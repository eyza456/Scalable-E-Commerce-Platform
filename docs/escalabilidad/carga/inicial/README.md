# Primera medicion multinstancia

Primera carga aprobada: 16.358 solicitudes medidas, 934 compras con calentamiento,
30 objetivos aprobados. Se conserva sin modificar fechas, muestras ni hashes.

El driver de carga posteriormente heredo la espera HTTP del driver de independencia
y la comprobacion de escalado 2/3/1/2 de los seis servicios. Se repitio la misma
carga y sus objetivos; el resultado vigente se guarda un nivel arriba. Los
microservicios y el overlay no cambiaron entre ambas mediciones.

Los hashes de este informe identifican el instrumento inicial y las fuentes
copiadas, incluidos archivos entonces agregados a Git. No se presentan como
hashes del driver posterior. La referencia de una sola instancia, independiente
de estas dos ejecuciones, sigue en `docs/rendimiento/`.

`instrumento.py` conserva exactamente el driver inicial: su SHA-256 se verifica
contra el registrado como `tests/multinstance_load.py`. Es una copia historica,
no un comando para ejecutar desde esta carpeta. El driver vigente de `tests/`
incorpora la espera de disponibilidad y la verificacion ampliada.
