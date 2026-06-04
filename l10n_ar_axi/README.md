# Módulo de Ajuste por Inflación — `l10n_ar_axi`
### Documentación funcional para el usuario

---

## ¿Qué hace este módulo?

Permite realizar el **ajuste integral por inflación contable** según la RT 6 de la FACPCE. El proceso reexpresa los saldos de las cuentas no monetarias al cierre del período, utilizando los índices IPC publicados por INDEC, y genera automáticamente el asiento contable de ajuste con su contrapartida en la cuenta RECPAM.

---

## Configuración inicial

Antes de usar el módulo por primera vez, ir a **Contabilidad → Configuración → Ajustes**, sección **Ajuste por Inflación**, y completar:

| Campo | Descripción |
|---|---|
| **Cuenta RECPAM** | Cuenta contable usada como contrapartida del asiento de ajuste |
| **Etiqueta cuentas no monetarias** | Etiqueta `AXI_NO_MONETARIA` — identifica las cuentas a reexpresar |
| **Diario de ajuste** | Diario propuesto por defecto al crear un batch (se puede cambiar en cada batch) |
| **Diarios excluidos del reporte** | Diarios que se excluyen por defecto en el reporte comparativo (ej: apertura, saldos iniciales) |

### Etiquetar cuentas no monetarias

Ir a **Contabilidad → Configuración → Plan de cuentas**, abrir cada cuenta no monetaria (bienes de uso, inventarios, patrimonio, etc.) y agregar la etiqueta `AXI_NO_MONETARIA` en el campo **Etiquetas**.

---

## Índices IPC

El módulo viene con los índices precargados desde **diciembre 2024 hasta febrero 2026**. Para períodos posteriores, cargar manualmente desde **Contabilidad → Ajuste por Inflación → Índices IPC**.

**Reglas:**
- La fecha debe ser siempre el **último día del mes** (el módulo lo valida)
- El valor es el **índice acumulado** publicado por INDEC, no la variación porcentual
- Deben estar cargados **todos los meses** desde el inicio del ejercicio hasta el mes de cierre del batch

---

## Proceso de ajuste — Batch

### 1. Crear un batch
Ir a **Contabilidad → Ajuste por Inflación → Batches** y crear uno nuevo.

| Campo | Descripción |
|---|---|
| **Fecha de cierre** | Último día del mes a ajustar (ej: 31/12/2025) |
| **Diario** | Se propone el configurado por defecto; se puede cambiar |

### 2. Calcular y contabilizar
Presionar **Calcular y contabilizar**. El módulo:

1. Toma todas las líneas contables **posteadas** del ejercicio fiscal vigente en cuentas con etiqueta `AXI_NO_MONETARIA`
2. Para cada línea, aplica el coeficiente `IPC cierre / IPC mes del movimiento`
3. Acumula el delta por cuenta
4. Genera el asiento de ajuste con contrapartida en RECPAM
5. Postea el asiento automáticamente

### 3. Verificar resultados
En la pestaña **Resultados** del batch se puede ver el detalle por cuenta:

| Columna | Descripción |
|---|---|
| **Base Nominal** | Saldo histórico de la cuenta en el período |
| **Coef Aplicado** | Coeficiente promedio ponderado (informativo) |
| **Monto Ajustado** | Saldo reexpresado a moneda de cierre |
| **Delta Ajuste** | Diferencia contabilizada |

### Reversión
Si se necesita corregir, usar el botón **Volver a borrador** — elimina el asiento generado y los resultados, dejando el batch listo para recalcular.

---

## Reporte Sumas y Saldos Comparativo

Permite comparar el balance **histórico** (sin ajuste) contra el balance **ajustado** (incluyendo el asiento AXI) para el período seleccionado.

### Cómo ejecutarlo
Ir a **Contabilidad → Ajuste por Inflación → Sumas y Saldos Comparativo**.

| Campo | Descripción |
|---|---|
| **Compañía** | Compañía a analizar |
| **Fecha de corte** | Fecha hasta la cual se calculan los saldos |
| **Diarios a incluir** | Se precarga con todos los diarios excepto los excluidos en configuración y el diario AXI; se puede ajustar por consulta |

Presionar **Exportar XLSX** para descargar el reporte.

### Estructura del reporte

| Columna | Descripción |
|---|---|
| **Cuenta** | Código de cuenta |
| **Descripción** | Nombre de la cuenta |
| **Saldo Histórico** | Saldo sin considerar asientos AXI |
| **Saldo Ajustado** | Saldo incluyendo asientos AXI |
| **Diferencia** | Diferencia entre ambos (en verde si positiva, en rojo si negativa) |

El reporte toma el período desde el **inicio del ejercicio fiscal** hasta la fecha de corte, respetando la configuración de cierre fiscal de la compañía.

---

## Notas importantes

- El cálculo del ajuste es **movimiento a movimiento**, usando el IPC del fin de mes de cada apunte. El coeficiente mostrado en los resultados es un promedio ponderado informativo, no un input del cálculo.
- Si falta algún índice IPC para un mes del período, el módulo lo indica con un error claro **antes** de calcular, sin modificar ningún dato.
- Los datos (índices, batches, resultados) viven en la base de datos y no se pierden al actualizar el módulo.
- Se pueden correr **múltiples batches** por ejercicio (ej: uno por mes). El reporte comparativo los considera todos automáticamente al incluir el diario AXI.

