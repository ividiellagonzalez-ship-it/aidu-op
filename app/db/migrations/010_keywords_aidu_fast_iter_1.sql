-- DESC: S13-keywords-iter-1 - Re-poblar AIDU Fast keywords con +22 nuevas
-- ============================================================
-- AIDU OP * MIGRACION 010 * S13 keywords iter-1
-- ============================================================
--
-- Tras analizar las 146 filas con linea_aidu=Otros del Lote 1 backfill,
-- se agregaron 22 keywords adicionales para capturar items legitimos que
-- escapaban al diccionario original (ver docs/changelog.md S13-keywords-iter-1).
--
-- Estrategia: DELETE de las 4 filas tipo=aidu_fast + INSERT OR REPLACE.
-- Idempotente: re-ejecutar produce mismo estado final.
-- Source of truth declarativo: config/keywords_aidu_fast.csv.

-- 1. Limpiar estado previo de aidu_fast (no afecta tipo=aidu_op)
DELETE FROM aidu_servicios_keywords WHERE tipo = 'aidu_fast';

-- 2. Re-insertar las 4 lineas con catalogo completo (CSV iter-1)
INSERT OR REPLACE INTO aidu_servicios_keywords
    (cod_servicio, nombre, keywords, hh_estimado_ignacio, hh_estimado_jorella, tipo)
VALUES
    ('FAST-FERRETERIA', 'Ferreteria y Construccion (AIDU Fast)', 'cemento,hormigon,fierro,acero,perfil,clavo,tornillo,tuerca,perno,alambre,martillo,taladro,sierra,llave,destornillador,pintura,brocha,rodillo,madera,tabla,ladrillo,bloque,fragüe,yeso,malla,cable,enchufe,interruptor,tuberia,fitting,codo,cañeria,valvula,manguera,herramienta,andamio,escalera,casco,guante,bota,cinta metrica,carretilla,saco arena,gravilla,bisagra,candado,silicona,sellador,pegamento construccion,construccion,iluminacion,luminaria,led,arido,alcantarillado,mejoramiento', 0, 0, 'aidu_fast'),
    ('FAST-ASEO', 'Aseo (AIDU Fast)', 'detergente,jabon,cloro,desinfectante,limpiador,escobillon,escoba,trapero,mopa,paño,papel higienico,toalla,servilleta,bolsa basura,dispensador,sanitizante,alcohol gel,lavaloza,suavizante,cera,lustramuebles,ambientador,desodorante,insecticida,desratizador,balde,esponja,guante latex,mascarilla,papel toalla,contenedor,pala,sopapo,limpia vidrios,antibacterial,desincrustante,virutilla,detergente liquido,toalla nova,bolsa basura industrial,alcohol isopropilico,materiales aseo,materiales y articulos de aseo,lavado,planchado', 0, 0, 'aidu_fast'),
    ('FAST-OFICINA', 'Oficina (AIDU Fast)', 'papel,resma,hoja,cuaderno,libreta,lapiz,lapicera,boligrafo,plumon,marcador,corrector,goma,sacapunta,regla,tijera,pegamento,cinta adhesiva,archivador,carpeta,separador,folder,sobre,etiqueta,post-it,perforadora,corchetera,corchete,clip,chinche,cartulina,block,agenda,calendario,tinta,toner,cartucho,resaltador,libro acta,papeleria,utiles escritorio,pendon,impresion logos,materiales de oficina', 0, 0, 'aidu_fast'),
    ('FAST-EQUIPAMIENTO', 'Equipamiento (AIDU Fast)', 'computador,notebook,laptop,monitor,teclado,mouse,impresora,escaner,proyector,pantalla,escritorio,silla,mesa,estante,mueble,archivador metalico,lockers,refrigerador,microondas,hervidor,cafetera,ventilador,calefactor,aire acondicionado,televisor,telefono,central telefonica,ups,regulador,switch,router,disco duro,memoria ram,procesador,tablet,kardex,estanteria,mueble oficina,computacional,computacion,audio,amplificacion,mobiliario,generador', 0, 0, 'aidu_fast');
