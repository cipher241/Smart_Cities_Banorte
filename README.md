# Smart Cities Banorte

Este repositorio contiene el proyecto "Smart Cities Banorte", una colección de recursos, bases de datos y código de apoyo orientados a soluciones de ciudades inteligentes relacionadas con análisis de datos urbanos, conectividad IoT y visualización. El objetivo es reunir ejemplos, scripts y documentación de servicios como agua, energía o transporte que faciliten pruebas de concepto aplicables a despliegues en entornos urbanos.

## Objetivos

- Hacer uso de analisis de datos mediante el uso de APIs con IAs para poder obtener conclusiones con su apoyo.
- Proveer utilidades para procesamiento, normalización y visualización de datos urbanos.
- Documentar arquitecturas y flujos de datos recomendados para soluciones de Smart Cities.

## Opt Ins

- Gemini API: Hacemos uso de una API de Gemini para que consuma una gran cantidad de datos en una base de datos para poder analizarlos y generar conclusiones rapida e independientemente del usuario.
- Snowflake: Utilizamos Snowflake de forma en la que cuando se sube un archivo de PDF a la página web, este archivo se envía a Snowflake donde se organizan y formatizan los datos, después se extrae el archivo formateado para que sea alimentado posteriormente a Gemini.

## Tecnologías (sugeridas)

- Ingesta: Gemini API.
- Procesamiento: Python, Node.js, 
- Almacenamiento: Snowflake o PostgreSQL
- Visualización: HTML, Javascript

## Cómo empezar (guía rápida)

1. Clona el repositorio:

   git clone https://github.com/cipher241/Smart_Cities_Banorte.git

2. Crea la estructura de carpetas sugerida y agrega ejemplos en `examples/`.


## Contribuir

- Abre issues para proponer funcionalidades o reportar bugs.
- Crea ramas con prefijo `feature/` o `fix/` y envía pull requests hacia `main`.
- Incluye pruebas mínimas y documentación para nuevas funcionalidades.

## Documento SRS (En inglés)
https://docs.google.com/document/d/1_rCxEN6-rxgDn4kplLef7FnRG-kruDJ6TOAKhkO70J8/edit?usp=sharing 

## Licencia

Se está considerando añadir una licencia como MIT o Apache-2.0.

## Contacto

Para preguntas o acceso adicional, contacta a los mantenedores del repositorio.

