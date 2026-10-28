# Primera optimizacion Outbox - c81a190

Drenaje inmediato tras lote completo, con pausa original de cinco segundos. Objetivos intactos. Resultado: p95 de compra 10,203 s, aun sobre 10 s; integridad aprobada. Se conserva esta ejecucion intermedia antes de reducir espera en vacio y reutilizar conexiones del broker.

Las rutas de hashes se refieren al checkout de la ejecucion historica, no al codigo vigente. El informe y los datos de esta carpeta no se regeneran con el resultado final.
