# Inventory Count Management — Odoo 19

**Versión:** 6.4.0  
**Autor / mantenimiento:** Oscar Morocho  
**Módulo técnico:** `setu_inventory_count_management`  
**Licencia:** OPL-1

## Objetivo

Este módulo gestiona el conteo físico de inventario con un proceso controlado y auditable. Mantiene el flujo administrativo de planificación, sesiones, revisión, aprobación, reconteo y ajuste, pero incorpora una experiencia específica para bodegueros que trabajan desde **celular o PDA**.

## Flujo recomendado

1. El supervisor crea un **Inventory Count** y define almacén, ubicación raíz, productos, aprobador y política del conteo.
2. Se crean una o varias **sesiones** y se asignan a los contadores.
3. El bodeguero abre **Conteo móvil / PDA**.
4. Escanea la **ubicación** una sola vez; permanece activa mientras trabaja en el mismo rack/bin.
5. Escanea el **producto**.
6. Si el producto tiene trazabilidad, escanea el **lote o número de serie**.
7. Para productos normales o por lote ingresa la **cantidad física** encontrada y confirma. Para seriales, cada lectura equivale a una unidad.
8. Continúa con el siguiente producto o cambia de ubicación.
9. Al terminar, envía/finaliza la sesión.
10. El supervisor revisa discrepancias, aprueba, rechaza o solicita **reconteo**.
11. Al completar todas las sesiones, se aprueba el Inventory Count y se genera/aplica el ajuste correspondiente.

## Interfaz móvil / PDA

La vista móvil elimina información administrativa que no necesita el contador y prioriza:

- Progreso del conteo.
- Ubicación activa.
- Próximo paso a ejecutar.
- Escaneo de ubicación, producto, lote y serie.
- Campo grande para cantidad física.
- Últimos productos contados.
- Acciones rápidas para cambiar ubicación, cancelar producto, pausar y finalizar.

La lógica de captura es común para lector PDA del teléfono, lector integrado de PDA y lectores Bluetooth/USB que envían el código al flujo de barcode.

## Controles y mejoras incluidas

- Conteo ciego configurable.
- Sesiones single y multiusuario.
- QR/código de barras para ubicación y productos.
- Lotes y números de serie.
- Control de seriales duplicados.
- Cantidad física directa para productos normales/lotes.
- Tolerancia por cantidad, porcentaje y valor.
- Clasificación de discrepancias.
- Autoaprobación configurable para coincidencias o diferencias dentro de tolerancia.
- Reconteos independientes.
- Auditoría de capturas y modificaciones manuales.
- Política de movimientos durante conteos.
- Conciliación de movimientos posteriores al escaneo por producto, ubicación, compañía y lote cuando corresponda.
- Protección contra generación duplicada de ajustes.
- Acceso de ajustes restringido a responsables del conteo.
- Dashboard y reportes de discrepancias, sesiones y desempeño.

## Políticas de movimientos durante conteo

Según la operación se puede permitir, conciliar o bloquear movimientos en las ubicaciones que están siendo contadas. Si la operación no puede detenerse, use la política de conciliación para considerar entradas y salidas realizadas después del momento de captura.

## Conteo ciego

Cuando está activo, el contador no debe utilizar la existencia teórica como referencia. Las cantidades y diferencias se mantienen disponibles para los cálculos y para el supervisor, pero se ocultan durante la ejecución del conteo para reducir sesgo.

## Actualización

Copie/reemplace la carpeta `setu_inventory_count_management`, reinicie Odoo, actualice la lista de aplicaciones y ejecute **Upgrade** del módulo.

Antes de producción, ejecute los tests del módulo en la base o entorno Odoo 19 objetivo.

## Capturas

Las imágenes de `static/description/screenshots/` documentan el nuevo flujo móvil/PDA y sustituyen la documentación visual antigua.

## Nota de origen

Esta versión conserva el nombre técnico y la licencia del módulo base adquirido originalmente. Las mejoras, ajustes, nueva interfaz móvil/PDA, documentación y mantenimiento de esta versión están identificados bajo Oscar Morocho.



## Simulación desde celular

Para validar el proceso antes de disponer de la PDA, abra **Conteo móvil / PDA** desde un teléfono y active **Simular lectura desde este celular**. Escriba o pegue un código de barras real y pulse **Procesar**.

Esta acción ejecuta la misma lógica `on_barcode_scanned()` que recibe el código del lector físico. Permite probar producto, lote, serie, cantidades, artículos no esperados y finalización del conteo. No utiliza cámara y está pensado únicamente como herramienta de prueba.


## Flujo PDA actual

El conteo no precarga productos ni consulta existencias al crear una sesión. El supervisor crea el conteo, selecciona ubicación y asigna al bodeguero. La sesión inicia vacía y las líneas se generan únicamente cuando se escanea un producto, lote o serie y se confirma su cantidad física.

Esto reduce el tiempo de creación de sesiones y evita cargar grandes volúmenes de productos que quizá no sean necesarios durante la operación.

## Lectura QR de lote

La pantalla PDA reconoce las etiquetas individuales generadas con el formato:

`ARTICULO/LOTE/CANTIDAD`

Ejemplo:

`B2050TE0712R03I/LOT260827001/15.10`

En una sola lectura se identifica el producto, se valida el lote y se propone la cantidad indicada por la etiqueta. El operador puede ajustar esa cantidad antes de confirmar el conteo físico.

El artículo se busca por referencia interna (`default_code`) o código de barras. Un mismo producto y lote no puede registrarse dos veces dentro de la misma sesión y ubicación: si se vuelve a escanear, el sistema muestra una advertencia y conserva la línea ya registrada.

## Interfaz móvil de conteo

El modo **Conteo PDA** está diseñado primero para celulares y terminales PDA. La pantalla muestra únicamente la información necesaria para la operación:

1. Ubicación actual.
2. Estado de lector listo.
3. Lectura QR/código.
4. Producto y lote identificados.
5. Cantidad física con teclado numérico.
6. Confirmación.

Cuando un Producto + Lote ya fue registrado en la misma sesión, la pantalla muestra una advertencia grande **YA ESCANEADO** y no genera una nueva línea.

