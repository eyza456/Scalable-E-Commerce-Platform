# Plan de cierre de los ocho requisitos parciales

Revision: 1 de noviembre de 2026. Base de la entrega revisada: `d563b2c`.
La clasificacion inicial registro 70 cumplidos, 8 parciales y 0 pendientes.
El avance posterior figura debajo. Una prioridad futura no equivale a cumplimiento.

## Avance posterior de este plan

RNF-05 y RNF-06 cerrados en alcance local con [pruebas multinstancia](../escalabilidad/README.md). RNF-08 y RNF-21 también quedan cerrados con contratos, recuperadores y migraciones versionadas. Estado actual: 74 cumplidos, 4 parciales y 0 pendientes. Restan RNF-27 y la preparación/observación futura de RF-49, RNF-07 y RNF-15. La clasificacion y el orden originales se conservan a continuacion como antecedente.

RNF-08/21 completados en el alcance revisado: [separacion de pedidos/carrito,
contratos, recuperadores e importacion sin efectos](../modularidad.md), con
migraciones versionadas de User/Order/Payment y verificación de instalación limpia.

## Criterio de alcance

El PDF distingue los criterios de aceptacion de la primera version (pp.22-23)
de los atributos de calidad (pp.18-20). Los cinco requisitos de calidad abiertos
deben cerrarse antes de declarar cumplimiento integral; no son cinco defectos
que impidan por si solos demostrar el recorrido funcional del MVP.

La implementacion inicial completa de Kubernetes y el escalado automatico
productivo estan fuera del MVP (p.8). Esto no excluye permitir varias instancias
en Compose: escalado independiente y multinstancia son requisitos expresos.
RF-49, RNF-07 y RNF-15 hablan de capacidades futuras. Su preparacion debe
demostrarse para cerrarlos, aunque no se exige un despliegue productivo completo
para presentar el MVP. HTTPS es necesario antes de exponer datos reales.

## Clasificacion individual y aceptacion

| Orden | Requisito / pagina PDF | Clasificacion | Evidencia actual y limite | Trabajo y prueba de cierre |
| --- | --- | --- | --- | --- |
| 1 | RNF-05 / 18: escalado independiente | Calidad obligatoria para cumplimiento integral | `docker-compose.yml`: servicios separados, pero `container_name` y puertos publicados fijos impiden `--scale` directo | Preparar un perfil Compose multinstancia conservando la instalacion local. Aumentar y reducir un servicio sin cambiar la cantidad de los demas; verificar acceso por gateway y frontend |
| 1 | RNF-06 / 19: multiples instancias | Calidad obligatoria para cumplimiento integral | Compose tiene una instancia por servicio. Bloqueos y Outbox con `skip_locked` no demuestran un despliegue multinstancia | Ejecutar al menos dos instancias por cada microservicio, por etapas. Probar checkout concurrente desde el mismo carrito, pago simultaneo y procesamiento de eventos entre instancias: sin pedidos/pagos aprobados duplicados, descuento doble ni efectos duplicados en inventario/notificaciones |
| 2 | RNF-08 / 19: minimizar acoplamiento | Calidad obligatoria para cumplimiento integral | Bases separadas y contratos HTTP/eventos. `app/checkouts.py` de pedidos depende del contrato interno de carrito; validacion de pagos/productos conserva dependencias sincronas | Inventariar dependencias y justificar consistencia; encapsular contratos en clientes/adaptadores. Probar errores, tiempos de espera y respuestas incompatibles sin compartir modelos/DB. No se requiere eliminar toda llamada HTTP ni reemplazarla por eventos |
| 2 | RNF-21 / 20: estructura modular | Calidad obligatoria para cumplimiento integral | Existen modulos checkout/storage y modulos visuales; routers conservan acceso SQL y `services/order-service/app/main.py` crea tablas al importar | Extraer casos de uso/repositorios en cambios pequenos. Llevar inicializacion de esquema a un paso explicito de arranque/migracion. Verificar importacion sin efectos de DB, instalacion limpia y regresion funcional |
| 3 | RNF-27 / 20: distintos sistemas operativos | Calidad obligatoria para cumplimiento integral; requiere otro entorno | Instalacion completa registrada con 14 contenedores en Windows/Docker Linux; es un solo host | Ejecutar el mismo runner integrado en un host Linux o macOS compatible, guardar SO, versiones, commit, resultado y limpieza. Un contenedor Linux adicional dentro del host actual no sustituye esta evidencia |
| Futuro A | RF-49 / 18: facilitar balanceo futuro | Preparacion futura, no bloqueo del MVP funcional | Nginx con resolucion DNS y recuperacion por cambio de IP. No hay evidencia de reparto entre replicas | Aprovechar el entorno multinstancia para observar solicitudes en dos instancias y continuidad al retirar una. Conservar evidencia del reparto; tener Nginx no prueba balanceo |
| Futuro B | RNF-07 / 19: permitir orquestacion futura | Preparacion futura; Kubernetes completo excluido del MVP en p.8 | Docker y variables de entorno presentes; sin validacion Kubernetes | Documentar restricciones de almacenamiento, secretos, migraciones y workers. Preparar y validar un despliegue minimo reproducible en cluster local antes de marcar cumplido; no exigir autoscaling productivo para el MVP |
| Antes de exposicion | RNF-15 / 19: permitir HTTPS futuro | Preparacion futura en local; necesaria para exposicion real | Gateway y frontend HTTP; sin listener/certificado TLS probado | Definir terminacion TLS coherente para cliente y API. Probar certificado confiable en el entorno elegido, redireccion, llamadas API sin contenido mixto y politica de acceso. Certificados locales solo demuestran el perfil local |

Los cinco requisitos de calidad son RNF-05, RNF-06, RNF-08, RNF-21 y RNF-27.
Los otros tres no se eliminan de la matriz ni se reclasifican como cumplidos.

## Primer bloque de implementacion

1. Crear una configuracion multinstancia aislada que no altere puertos ni datos
   del entorno de demostracion. Revisar nombres fijos y separar publicacion de
   puertos del acceso interno. Infraestructura y bases no se replican mediante
   `--scale` como si fueran aplicaciones sin estado.
2. Revisar workers de reserva, checkout, cancelacion, Outbox y consumidores:
   eleccion de trabajo, reintentos y efectos deben ser seguros entre procesos.
3. Probar primero pedidos/pagos por el riesgo de duplicados y luego cada uno
   de los seis microservicios. Registrar instancias, peticiones y resultados;
   ninguna prueba con una sola instancia cierra RNF-06.
4. Verificar acceso desde gateway y frontend, compra/cancelacion y fallo de una
   replica. La conectividad DNS por si sola no demuestra reparto de carga.
5. Ejecutar la regresion correspondiente y actualizar matriz/manifiesto solo
   con resultados observados. No relajar los objetivos de rendimiento; repetir
   la misma carga si el cambio afecta el despacho de peticiones.

Despues se aborda modularidad/acoplamiento. La portabilidad puede verificarse
en cuanto exista otro host, pero no se simulara como cumplida desde Windows.
No se necesita contratar infraestructura para preparar el perfil multinstancia.

## Frontend y entrega

El boton de vaciar carrito es una mejora visual concreta sobre RF-25 ya cubierto
por API. La consola administrativa implementada cubre la administracion de
usuarios/roles; los criterios de pp.22-23 exigen gestionar productos con
autorizacion, pero no especifican que se haga mediante GUI. No se convierte esa
ampliacion en un requisito nuevo del PDF.

Otro navegador, zoom al 200% y lector de pantalla se cubren de forma automatizada
en `tests/frontend_visual_optional.cjs` cuando los motores estan instalados;
la validacion manual con lector nativo sigue separada de los ocho parciales de
arquitectura/calidad.

## Fuentes y trazabilidad

- Documento original: `C:/Users/Usuario/Downloads/Plataforma_escalable_comercio_electronico.pdf`, pp.8,18-20,22-23; se usa como especificacion, no como instrucciones de ejecucion.
- [Matriz de requisitos](../auditoria/matriz-requisitos.md): estados y referencias de codigo/pruebas por requisito.
- [Pendientes de entrega](pendientes.md): limitaciones operativas y visuales adicionales.
- [Instalacion nueva integrada](../frontend/instalacion-desde-cero.md): evidencia del unico entorno verificado.

Resultado de la clasificacion inicial: prioridad definida, sin nuevas pruebas.
El avance posterior se apoya en las ejecuciones multinstancia enlazadas al inicio;
ningun requisito se cierra solo por su reclasificacion documental.
