# Sprint S14 (CANDIDATO) — Expansión AIDU Fast a línea Salud

**Estado**: 🟡 **Por decidir** (no aprobado).
**Decisor**: Director Ejecutivo.
**Origen**: hallazgo del Lote 1 backfill de S13 (2026-05-22).
**Tipo**: estratégico-comercial, no técnico. Requiere análisis de mercado y
capital de trabajo antes de comprometer sprint técnico.

---

## Hallazgo del Lote 1 que motiva este sprint

Al analizar las 146 filas con `linea_aidu='Otros'` del primer lote de
backfill (`backfill_1`, ventana 2026-05-15 → 2026-05-21, 191 items
totales en O'Higgins), la composición real del mercado regional bajo
1.000 UTM resultó ser:

| Segmento del mercado regional | % aproximado | Comprador típico |
|---|---:|---|
| **Salud (médico + dental + veterinario)** | **~55%** | Hospital San Fernando, Servicio Salud O'Higgins, odontología municipal, veterinaria municipal |
| Alimentación escolar (JUNAEB / jardines) | ~7% | Municipalidades (Lituche, etc.) para programas alimentarios |
| Servicios profesionales | ~10% | Capacitaciones, contratación profesional, coffee break, mensajería |
| Vehículos / transporte | ~4% | Convenios de arriendo, suministro mantención |
| **Nicho AIDU Fast (Ferretería + Aseo + Oficina + Equipamiento)** | **~24%** | Municipalidades, escuelas |
| Otros (gift cards, eventos, anexos vacíos) | ~3% | — |

El criterio #3 del spec original ("≥70% items no-Otros") **NO se cumple
en O'Higgins** porque el sector salud representa el 55% del mercado bajo
1.000 UTM, mucho mayor que los 4 rubros AIDU Fast actuales.

S13 ya redefinió el criterio (ver `docs/changelog.md → S13-keywords-iter-1`)
a "**≥80% cobertura dentro del scope AIDU Fast**", que sí se cumple.
Queda la decisión estratégica: **expandir el scope** vs **aceptar el nicho**.

---

## Hipótesis de expansión a Salud

Si AIDU Fast agregara una 5ª línea **"Salud"**, capturaría:
- ~75-80 items adicionales/lote de 7d (subiría no-Otros del 32% al ~70%).
- Mercado anual estimado regional (extrapolando 90d × 4): ~3.000-3.500
  adjudicaciones de salud bajo 1.000 UTM, con compradores recurrentes
  (Hospital San Fernando + SS O'Higgins ≈ 60% del volumen salud).
- Productos típicos: agujas, anestesias, gutapercha, balones dilatación,
  medicamentos genéricos, kits diagnóstico, suero fisiológico, gasa,
  mascarillas, EPP, materiales odontológicos.

---

## Preguntas estratégicas pendientes (NO técnicas)

### 1. Barreras regulatorias / licencias

- **¿Requiere AIDU Fast registro ISP** (Instituto de Salud Pública) para
  importar / distribuir insumos médicos en Chile? Probable: sí para
  dispositivos médicos clase II/III y medicamentos. **No**, para
  insumos básicos (gasa, agujas, jeringas, mobiliario clínico).
- **¿Existen certificaciones obligatorias** (ISO 13485 para dispositivos
  médicos, GMP para medicamentos)? Algunas líneas las requieren.
- **¿La compra pública por Mercado Público distingue compradores
  "salud"** vía algún campo / criterio especial en las licitaciones
  (ej. RUT del organismo, código de servicio)? Confirmar con la API.

### 2. Capital de trabajo y distribución

- **Stock mínimo viable**: ¿AIDU Fast importa/almacena, o opera como
  intermediario (drop-shipping desde proveedor mayorista)?
- **Tiempos de entrega**: los hospitales típicamente exigen entrega en
  24-72h. ¿AIDU Fast puede cumplir desde Rancagua sin bodega regional?
- **Cadena de frío**: medicamentos refrigerados (vacunas, sueros)
  requieren logística específica. ¿Scope incluye solo no-refrigerados?
- **Capital de trabajo**: las adjudicaciones de salud bajo 1.000 UTM
  típicamente tienen plazos de pago 30-60 días post-recepción. AIDU
  Fast debe financiar inventario en el ínterin.

### 3. Análisis competitivo

- **Quién gana hoy las adjudicaciones salud O'Higgins?** Cruzar
  `inteligencia_precios.proveedor_rut` con `linea_aidu='Otros'` y
  `organismo_region LIKE '%Libertador%'` post-Lote-12. Esperable:
  distribuidores nacionales (Socofar, Vasconia, Tecnofar, Salcobrand).
- **¿Hay nicho regional**? Proveedores locales que sólo atienden
  Hospital San Fernando o municipios — son candidatos a competencia
  más débil que distribuidores nacionales.
- **Márgenes típicos salud bajo 1.000 UTM**: estimar de la data tras
  S13 completa. Probablemente más estrechos que ferretería/oficina por
  la dominancia de pocos proveedores especializados.

### 4. Validación operativa antes de S14

- **Primera adjudicación en una de las 4 líneas actuales**: AIDU Fast
  debe ganar al menos UNA licitación L1/LE/CO antes de comprometer
  capital a expansión Salud. Es el gate operacional explícito del
  Director.
- **Métricas a validar tras la primera adjudicación**: márgenes reales,
  tiempos de cobranza, cantidad de oferentes que compitieron, qué
  reclamos / observaciones tuvo la oferta.

---

## Alcance preliminar SI se aprueba S14

(Sólo orientativo, sujeto a re-spec completa antes de implementación.)

1. **Nueva línea `Salud`** en `aidu_servicios_keywords` con
   `tipo='aidu_fast'`, `cod_servicio='FAST-SALUD'`. Keywords semilla
   extraídas del análisis post-Lote-12 (esperable: ~50-70 keywords con
   sub-rubros odontología / medicamentos / EPP / insumos quirúrgicos).
2. **Refactor de `categorizador_aidu_fast.LINEAS_AIDU_FAST`**: pasar de
   4 a 5 líneas. Tests deben re-validar acierto ≥80% por línea.
3. **Sub-rubros opcionales dentro de Salud**: si Salud captura > 30% del
   universo, conviene sub-dividirla (odontología vs medicamentos vs EPP)
   para que el buscador Streamlit no sature.
4. **Pantalla Streamlit**: agregar filtro de línea con la nueva opción.
   Tab "Productos más comprados" se segmenta automáticamente.
5. **Diccionario CSV ampliado** + migración 011 con `INSERT OR REPLACE`.
6. **Documentación del riesgo regulatorio**: capítulo nuevo en
   `docs/sprints/AIDU_Op_S14_*.md` (decidir título final post-aprobación)
   con la decisión del Director sobre alcance regulatorio (ej. "AIDU Fast
   solo opera sub-rubros que NO requieren ISP").

---

## Out of scope explícito de S14 (sea cual sea la decisión)

- Medicamentos controlados (psicotrópicos, oncológicos): regulación
  especial, márgenes bajos, riesgo alto.
- Dispositivos médicos clase III (alta complejidad: prótesis, marcapasos).
- Insumos hospitalarios de alta tecnología (resonancias, equipos de
  diagnóstico): mercado dominado por importadores grandes.
- Veterinaria: pertenece a línea distinta, no es "Salud humana".

---

## Acciones del Director antes de aprobar S14

- [ ] Esperar a que termine el Backfill de S13 (Lotes 2-12) para tener
      data anual completa, no solo 1 semana.
- [ ] Validar con Lote 12 cerrado:
      - Conteo real de items "Otros" que sean salud (debería ser
        ~700-800 sobre 90 días).
      - Top 10 proveedores ganadores en salud O'Higgins.
      - Distribución de montos (mediana / p25 / p75 por sub-rubro).
- [ ] Ganar primera adjudicación en una de las 4 líneas AIDU Fast
      actuales (gate operacional explícito).
- [ ] Conversar con un distribuidor mayorista de insumos médicos
      (Socofar, Tecnofar, Vasconia) sobre términos de partnership /
      drop-shipping vs compra directa.
- [ ] Consultar con asesor legal/regulatorio sobre licencias ISP y
      tiempos típicos de obtención.
- [ ] Estimar capital de trabajo necesario para sostener un trimestre
      de operación pre-cobranza.

---

## Dependencia upstream

- ✅ S13 completo (en proceso).
- ⏳ Backfill 12/12 lotes terminado.
- ⏳ Primera adjudicación AIDU Fast cerrada.

**Branch sugerido cuando S14 se apruebe**: `feature/s14-linea-salud`.
