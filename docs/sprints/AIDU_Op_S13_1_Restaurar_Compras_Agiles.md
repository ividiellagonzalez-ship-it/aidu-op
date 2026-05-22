# Sprint S13.1 — Restaurar descarga de Compras Ágiles

**Estado**: BLOQUEADO (pendiente investigación nuevo endpoint MP).
**Prioridad**: Alta — la CA es estratégica para AIDU Fast (cliente B2G del holding).
**No bloqueante** para S13 MVP, que arranca con L1+LE+CO únicamente.
**Origen**: hallazgo lateral del reconnaissance S13 (2026-05-21).
**Reproductor**: `scripts/diagnostics/_recon_agil_check.py` (vive en feature branch
de S13, se elimina al cerrar S13.1).

---

## Resumen del hallazgo

El cliente actual `app/api/mercadopublico.py` invoca el endpoint
`/APISOCDS/AGIL/listar` para descargar Compras Ágiles. Con **ticket
productivo real**, las 15 combinaciones razonables (5 URLs × 3 formatos
de fecha) devuelven **HTTP 404** desde `api.mercadopublico.cl`, mientras
que el endpoint principal `/licitaciones.json` responde 200 OK con el
mismo ticket.

Tres tipos de body 404 distintos confirman que el problema es del lado del
gateway/IIS, no del ticket ni del formato de fecha:

| Body 404 observado | URL fuente | Interpretación |
|---|---|---|
| `<!DOCTYPE html>...The resource cannot be found.</title>` (IIS clásico) | `/APISOCDS/AGIL/listar` (3 variantes case) | Endpoint no enrutado en gateway. |
| XHTML 1.0 Strict | `/api/AGIL/listar` | Path legacy ya retirado. |
| `{"Codigo":404,"Mensaje":"Recurso no encontrado."}` | `/servicios/v1/publico/AGIL/listar` | API v1 estructurada responde que AGIL no es recurso válido bajo esa base. |

El sanity check del endpoint principal con el mismo ticket devolvió 337
adjudicaciones para 2026-05-19. Conclusión: **el ticket funciona, la red
funciona, el endpoint AGIL fue eliminado o movido a una nueva ubicación
que ninguna de las 5 variantes razonables alcanza**.

## Bug silencioso en producción

`_request_agil()` en `app/api/mercadopublico.py` trata HTTP 404 como
`logger.warning(...)` + `return None`. El cliente lo recibe como lista
vacía. El cron diario `descarga_mp_diaria.yml` reporta entonces "OK ·
n_nuevas: 0" cuando en realidad **no descarga ninguna Compra Ágil desde
hace tiempo indeterminado**.

S13 incluye un side-fix mínimo para que este caso quede explícito en el
log de ingesta. Ver sección **Side-fixes en el PR de S13** abajo. La
restauración del endpoint sigue siendo trabajo de S13.1.

## Alcance del sprint S13.1

### Objetivo único

Que el cliente vuelva a descargar Compras Ágiles desde una API pública
oficial de Mercado Público, con un test de integración que detecte
regresiones futuras.

### Investigación necesaria (no resuelta aún)

1. **Documentación oficial MercadoPúblico**: revisar
   <https://desarrolladores.mercadopublico.cl/> y similares por nueva
   API de Compras Ágiles. Puede haber migración a OAuth2, nuevo dominio
   (`apis.chilecompra.cl`?), o nueva nomenclatura.
2. **Hipótesis a probar** (todas con ticket productivo):
   - Nuevo path bajo el mismo dominio: `/agil/api/v2/`, `/compras-agiles/`,
     `/v2/agil/`, etc.
   - Nuevo dominio: `apis.chilecompra.cl`, `api2.mercadopublico.cl`.
   - El endpoint movido al path principal con un parámetro: por ejemplo
     `/licitaciones.json?fecha=...&estado=adjudicada&tipo=AGIL`.
   - El portal público sigue mostrando Ágiles, pero la API pública puede
     requerir registración de un nuevo ticket o pasar a "Mis Compras"
     autenticado (no ideal para nuestro caso, AIDU no es comprador).
3. **Última verificación de github commits del repo**: posible que en
   S12.x o anterior haya quedado una pista del cambio que aquí no vimos.

### Criterios de éxito S13.1

| # | Criterio | Umbral |
|---|---|---|
| 1 | Endpoint AGIL responde HTTP 200 con data JSON | ≥ 1 día con > 0 resultados |
| 2 | `listar_agiles_por_fecha` reincorporado al cron diario | Sin warning 404 en logs |
| 3 | Test de integración con mock del nuevo endpoint | Pasa |
| 4 | Test que falla si vuelve el 404 silencioso | Detecta regresión |
| 5 | `mp_ingesta_log` registra n > 0 por al menos 3 días seguidos | Validado en log real |
| 6 | Cobertura de monto_unitario en CA recuperada | Aceptar lo que la API entregue (se evalúa al ver el shape real) |
| 7 | Backfill 90 días de CA O'Higgins ejecutado y persistido a `inteligencia_precios` | n > 100 filas adicionales |

### Riesgos identificados

- **R1**: No existe API pública nueva para AGIL. **Mitigación**: dejar
  S13.1 abierto sin fecha; usar Licitalab para CA durante este período
  (decisión del Director).
- **R2**: La nueva API requiere registración de developer key.
  **Mitigación**: Director registra cuenta y obtiene nuevo ticket.
- **R3**: El cron diario tiene autenticación distinta. **Mitigación**:
  ver `.github/workflows/descarga_mp_diaria.yml` secretos.

### Out of scope explícito de S13.1

- Restaurar otros endpoints OCDS si están caídos (ej. APISOCDS/...).
- Cambiar de API v1 a v2 globalmente (S15 candidato).
- Backfill histórico previo a S13 (sólo backfill 90 días dentro del scope
  S13 una vez que el endpoint vuelva).

---

## Side-fixes en el PR de S13 (NO en S13.1)

Estos cambios mínimos van con el PR de S13 para que el bug deje de ser
silencioso, sin restaurar el endpoint (eso es S13.1):

1. `_request_agil()` clasifica logging:
   - HTTP 404 → `logger.warning("AGIL endpoint 404 — ver S13.1")`
   - HTTP 5xx/error → `logger.error(...)`
   - HTTP 200 con lista vacía → `logger.info(...)`
2. `mp_ingesta_log` recibe nueva columna `agil_endpoint_estado TEXT`
   con valores `'ok' | 'caido_404' | 'error_otro' | 'no_consultado'`
   (ALTER incluido en migración 009 de S13).
3. Dashboard de monitoreo (futuro) puede mostrar el estado AGIL sin
   investigación manual.

Cuando S13.1 cierre, el side-fix queda igual (sigue siendo útil para
detectar futuras caídas), pero el valor por defecto pasa a `'ok'`.

---

## Acciones del Director

- [ ] Asignar prioridad y semana de ejecución.
- [ ] Investigar documentación oficial de MercadoPúblico para nuevo
      endpoint AGIL.
- [ ] Si la nueva API requiere registración, obtener nuevo ticket.
- [ ] Confirmar si se mantiene Licitalab como cobertura provisoria de CA.

---

**Branch sugerido**: `feature/s13-1-restaurar-agil` (cuando S13.1 arranque).
**Dependencias upstream**: ninguna, S13.1 puede arrancar después de S13
sin esperar otros sprints.
