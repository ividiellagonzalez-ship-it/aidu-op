"""
Tests para el orden topológico del bootstrap a Turso (S12.1.5).

Cubre:
- _topological_sort: casos básicos, idempotencia, tie-break alfabético.
- _topological_sort: detección de ciclos.
- _build_dependency_graph: monkeypatch de _execute para mockear PRAGMA
  foreign_key_list, sin tocar Turso.
- Caso real con las 14 tablas de la seed (post SKIP_TABLES) — el orden
  debe poner mp_licitaciones_adj antes que mp_categorizacion_aidu y
  mp_licitacion_items, y aidu_proyectos antes que sus 5 hijas.

Ejecutar: pytest tests/test_bootstrap_topology.py -v
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_bootstrap_module():
    """Carga docs/migracion_inicial_turso.py como módulo, sin ejecutar main()."""
    path = REPO / "docs" / "migracion_inicial_turso.py"
    spec = importlib.util.spec_from_file_location("migracion_inicial_turso", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["migracion_inicial_turso"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def boot():
    return _load_bootstrap_module()


# ============================================================
# _topological_sort
# ============================================================
class TestTopologicalSort:

    def test_empty_graph(self, boot):
        assert boot._topological_sort({}) == []

    def test_single_node_no_deps(self, boot):
        assert boot._topological_sort({"a": []}) == ["a"]

    def test_no_dependencies_alphabetical(self, boot):
        # 3 nodos sin FKs: orden alfabético determinista
        graph = {"c": [], "a": [], "b": []}
        assert boot._topological_sort(graph) == ["a", "b", "c"]

    def test_simple_chain(self, boot):
        # a <- b <- c   (b depende de a, c depende de b)
        graph = {"a": [], "b": ["a"], "c": ["b"]}
        assert boot._topological_sort(graph) == ["a", "b", "c"]

    def test_multiple_children_one_parent(self, boot):
        # parent <- {child_b, child_a, child_c}: padre primero, hijos alfabéticos
        graph = {
            "parent": [],
            "child_b": ["parent"],
            "child_a": ["parent"],
            "child_c": ["parent"],
        }
        order = boot._topological_sort(graph)
        assert order[0] == "parent"
        assert order[1:] == ["child_a", "child_b", "child_c"]

    def test_diamond(self, boot):
        # root <- {a, b} <- bottom
        graph = {
            "root": [],
            "a": ["root"],
            "b": ["root"],
            "bottom": ["a", "b"],
        }
        order = boot._topological_sort(graph)
        assert order.index("root") < order.index("a")
        assert order.index("root") < order.index("b")
        assert order.index("a") < order.index("bottom")
        assert order.index("b") < order.index("bottom")

    def test_cycle_raises(self, boot):
        # Ciclo a <- b <- a
        graph = {"a": ["b"], "b": ["a"]}
        with pytest.raises(ValueError, match="Ciclo detectado"):
            boot._topological_sort(graph)

    def test_self_loop_raises(self, boot):
        # Self-loop puro a <- a (no debería pasar por _build_dependency_graph,
        # que descarta self-refs, pero _topological_sort sólo recibe el grafo)
        graph = {"a": ["a"]}
        with pytest.raises(ValueError, match="Ciclo detectado"):
            boot._topological_sort(graph)

    def test_idempotent(self, boot):
        # Misma entrada → misma salida (tie-break alfabético determinista)
        graph = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}
        out1 = boot._topological_sort(graph)
        out2 = boot._topological_sort(graph)
        assert out1 == out2

    def test_real_aidu_schema(self, boot):
        """Replica el grafo real del schema aidu-op (15 tablas - _migrations)."""
        graph = {
            # padres independientes
            "aidu_proyectos": [],
            "mp_licitaciones_adj": [],
            "aidu_parametros": [],
            "aidu_servicios_keywords": [],
            "aidu_sugerencias_tarifario": [],
            "mp_ingesta_log": [],
            "mp_organismos_perfil": [],
            # hijos de aidu_proyectos
            "aidu_chat_ia": ["aidu_proyectos"],
            "aidu_checklist": ["aidu_proyectos"],
            "aidu_comunicaciones": ["aidu_proyectos"],
            "aidu_documentos": ["aidu_proyectos"],
            "aidu_propuesta_secciones": ["aidu_proyectos"],
            # hijos de mp_licitaciones_adj
            "mp_categorizacion_aidu": ["mp_licitaciones_adj"],
            "mp_licitacion_items": ["mp_licitaciones_adj"],
        }
        order = boot._topological_sort(graph)
        # Padres antes que hijos
        assert order.index("aidu_proyectos") < order.index("aidu_chat_ia")
        assert order.index("aidu_proyectos") < order.index("aidu_propuesta_secciones")
        assert order.index("mp_licitaciones_adj") < order.index("mp_categorizacion_aidu")
        assert order.index("mp_licitaciones_adj") < order.index("mp_licitacion_items")
        # Sin tablas faltantes
        assert set(order) == set(graph.keys())
        # Los dos padres con hijos deben aparecer antes de TODOS sus hijos.
        # (El tie-break alfabético de Kahn intercala independientes con hijos
        # recién liberados — lo importante es padre→hijo, no que todos los
        # independientes aparezcan en bloque al inicio.)
        for hija in ["aidu_chat_ia", "aidu_checklist", "aidu_comunicaciones",
                     "aidu_documentos", "aidu_propuesta_secciones"]:
            assert order.index("aidu_proyectos") < order.index(hija)
        for hija in ["mp_categorizacion_aidu", "mp_licitacion_items"]:
            assert order.index("mp_licitaciones_adj") < order.index(hija)


# ============================================================
# _build_dependency_graph
# ============================================================
class TestBuildDependencyGraph:

    def _stub_pragma(self, fk_map: dict[str, list[str]]):
        """
        Devuelve una función que reemplaza a _execute para mockear PRAGMA
        foreign_key_list. fk_map: {tabla: [tablas_padre]}.
        """
        def fake_execute(http_url, headers, statements):
            stmt = statements[0].get("sql", "")
            # Match: PRAGMA foreign_key_list("tbl")
            for tbl, parents in fk_map.items():
                if f'"{tbl}"' in stmt:
                    rows = []
                    for i, p in enumerate(parents):
                        # cells: id, seq, table, from, to, on_update, on_delete, match
                        rows.append([
                            {"value": str(i)},   # id
                            {"value": "0"},      # seq
                            {"value": p},        # table (parent)
                            {"value": "fk_col"}, # from
                            {"value": "pk_col"}, # to
                            {"value": "NO ACTION"},
                            {"value": "NO ACTION"},
                            {"value": "NONE"},
                        ])
                    return [{
                        "type": "ok",
                        "response": {"result": {"rows": rows}},
                    }]
            # tabla no listada → sin FKs
            return [{"type": "ok", "response": {"result": {"rows": []}}}]
        return fake_execute

    def test_no_fks(self, boot, monkeypatch):
        monkeypatch.setattr(boot, "_execute", self._stub_pragma({}))
        graph = boot._build_dependency_graph(None, None, ["a", "b", "c"])
        assert graph == {"a": [], "b": [], "c": []}

    def test_simple_fk(self, boot, monkeypatch):
        monkeypatch.setattr(boot, "_execute", self._stub_pragma({"child": ["parent"]}))
        graph = boot._build_dependency_graph(None, None, ["parent", "child"])
        assert graph == {"parent": [], "child": ["parent"]}

    def test_self_reference_filtered(self, boot, monkeypatch):
        # FK de la tabla a sí misma se descarta (no afecta orden inter-tablas)
        monkeypatch.setattr(boot, "_execute", self._stub_pragma({"a": ["a"]}))
        graph = boot._build_dependency_graph(None, None, ["a"])
        assert graph == {"a": []}

    def test_external_parent_filtered(self, boot, monkeypatch):
        # Si el padre no está en `tables`, la FK no se cuenta como dep en scope
        monkeypatch.setattr(boot, "_execute", self._stub_pragma({"child": ["external"]}))
        graph = boot._build_dependency_graph(None, None, ["child"])
        assert graph == {"child": []}

    def test_real_aidu_topology(self, boot, monkeypatch):
        # Mock con la topología real del schema aidu-op
        fk_map = {
            "aidu_chat_ia": ["aidu_proyectos"],
            "aidu_checklist": ["aidu_proyectos"],
            "aidu_comunicaciones": ["aidu_proyectos"],
            "aidu_documentos": ["aidu_proyectos"],
            "aidu_propuesta_secciones": ["aidu_proyectos"],
            "mp_categorizacion_aidu": ["mp_licitaciones_adj"],
            "mp_licitacion_items": ["mp_licitaciones_adj"],
        }
        monkeypatch.setattr(boot, "_execute", self._stub_pragma(fk_map))
        seed_tables = [
            "aidu_chat_ia", "aidu_checklist", "aidu_comunicaciones",
            "aidu_documentos", "aidu_parametros", "aidu_propuesta_secciones",
            "aidu_proyectos", "aidu_servicios_keywords",
            "aidu_sugerencias_tarifario", "mp_categorizacion_aidu",
            "mp_ingesta_log", "mp_licitacion_items", "mp_licitaciones_adj",
            "mp_organismos_perfil",
        ]
        graph = boot._build_dependency_graph(None, None, seed_tables)
        # Sanity: graph cubre todas las tablas
        assert set(graph.keys()) == set(seed_tables)
        # Hijos tienen exactamente el padre esperado
        assert graph["mp_categorizacion_aidu"] == ["mp_licitaciones_adj"]
        assert graph["aidu_chat_ia"] == ["aidu_proyectos"]
        # Independientes con lista vacía
        assert graph["aidu_parametros"] == []
        assert graph["mp_licitaciones_adj"] == []
        # Sort topológico sobre el grafo real produce orden viable
        order = boot._topological_sort(graph)
        assert order.index("mp_licitaciones_adj") < order.index("mp_categorizacion_aidu")
        assert order.index("mp_licitaciones_adj") < order.index("mp_licitacion_items")
        for hija in ["aidu_chat_ia", "aidu_checklist", "aidu_comunicaciones",
                     "aidu_documentos", "aidu_propuesta_secciones"]:
            assert order.index("aidu_proyectos") < order.index(hija)
