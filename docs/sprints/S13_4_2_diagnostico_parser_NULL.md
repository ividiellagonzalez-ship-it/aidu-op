# S13.4.2 — Diagnóstico del parser NULL (solo reporte, sin fix)

**Estado**: diagnóstico cerrado. Implementación del fix queda diferida a sprint posterior (sugerido S13.4.3).

## Contexto

Del análisis de calidad del Lote 1 (654 items), **106 items (16.2%)** tienen `precio_unitario` en NULL aunque sí tengan `cantidad` real. La hipótesis del Director era que el parser ignora una ruta alternativa del payload JSON.

## Lo que hace hoy el parser

`app/core/ingesta_inteligencia_precios.py:expandir_items` líneas 256-280 itera `entry["Items"]["Listado"]` y para cada ítem accede a `Adjudicacion.MontoUnitario` (o `montoUnitario` lowercase). Si `Adjudicacion` no existe o `MontoUnitario` es None/empty/0, `precio_unitario` queda NULL.

```python
adj_item = it.get("Adjudicacion") if isinstance(it.get("Adjudicacion"), dict) else None
if adj_item:
    precio_unitario = _safe_float(
        adj_item.get("MontoUnitario") or adj_item.get("montoUnitario")
    )
```

## Hipótesis del Director: ruta alternativa del payload

El spec sugiere que casos como `Hospital de Santa Cruz` con productos tipo `ISON0050 SONDA NASO GASTRICA` pueden tener `MontoUnitario` en `/Adjudicacion/MontoLineaAdjudicada` o equivalente.

## Inspección de la API (no concluyente sin muestreo real)

NO ejecuté llamadas API a 3 códigos específicos en este sprint (per spec sec 4.9: solo diagnóstico). Lo que sí confirmé del reconnaissance anterior (S13.4.1, donde sí peggé `3864-4-LE26`, `3997-21-LE26`, `1627-29-LE26`):

- **Estructura observada**: la API SÍ usa `Adjudicacion.MontoUnitario` directo. El parser actual la captura bien para esos 3 códigos.
- **Caso `3864-4-LE26` (3 contenedores)**: `MontoUnitario=$24M, Cantidad=1` (válido, no NULL).
- **Caso `3997-21-LE26` (contrato marco)**: `MontoUnitario=$1, Cantidad=20M` (contrato simbólico).
- **Caso `1627-29-LE26` (hospital)**: 13 ítems todos con `MontoUnitario` poblado.

## Hipótesis revisada (más probable)

El 16.2% de NULL probablemente NO se debe a una ruta alternativa, sino a **3 patrones distintos**, en orden de probabilidad:

1. **Item registrado SIN nodo `Adjudicacion`**: el comprador adjudicó la licitación pero el detalle del ítem específico quedó sin `Adjudicacion`. En la API se ve como `{"Correlativo": N, "Descripcion": "...", "Cantidad": X}` sin la rama `Adjudicacion`. El parser correctamente cae en NULL.

2. **`MontoUnitario` = 0 explícito**: algunos compradores registran items con `MontoUnitario=0` para items "sin costo" dentro de un convenio. El `_safe_float(0)` devuelve `0.0` que en SQLite/Pandas queda como 0 — no NULL. **Pero**: el código actual usa `or` con short-circuit: `adj_item.get("MontoUnitario") or adj_item.get("montoUnitario")` — **si `MontoUnitario=0`, el `or` se va a `montoUnitario` y devuelve None si no existe esa key**. Eso explica algunos NULL que deberían ser 0.

3. **`MontoUnitario` en formato string con coma decimal** (`"7.885,00"`): la API a veces serializa montos como strings localizados (es-CL). `_safe_float("7.885,00")` falla y devuelve None. El parser queda NULL en ese caso.

## Recomendación para sprint S13.4.3 (fix, no en este sprint)

1. **Fix patrón 2 (short-circuit del `or`)**: cambiar a `mu = adj_item.get("MontoUnitario"); mu = mu if mu is not None else adj_item.get("montoUnitario")`. Captura el `MontoUnitario=0` como 0 explícito.

2. **Fix patrón 3 (string localizado)**: en `_safe_float`, agregar try/except con `s.replace(".", "").replace(",", ".")` cuando el input es string con coma.

3. **No-fix patrón 1**: si el ítem no tiene `Adjudicacion`, no hay dato. Aceptar NULL.

## Estimación de recuperación

- Patrón 2 + 3: probable recuperar **40-70 items** de los 106 (38-66% del NULL).
- Patrón 1: irrecuperable (~36-66 items quedan NULL).

## Próximo paso sugerido

Sprint S13.4.3 con scope 30-45 min: aplicar los 2 fixes de `_safe_float` y el `or` short-circuit, agregar 4-5 tests con payloads sintéticos (MontoUnitario=0, MontoUnitario="7.885,00", Adjudicacion ausente, etc.), correr workflow de re-ingestar las 106 filas afectadas. Validar reducción del NULL ratio de 16% a ~7-10%.
