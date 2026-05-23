-- DESC: S13.4.2 - Lineas Salud + Materiales de Construccion + auditoria reclasificacion
-- ============================================================
-- AIDU OP * MIGRACION 011 * S13.4.2
-- ============================================================
--
-- Tras el diagnostico de calidad de los 654 items del Lote 1 (sprint S13.4.2),
-- se identifico que 270 items en linea_aidu=Otros son insumos medicos no
-- clasificados. Esta migracion:
--
-- 1) ALTER inteligencia_precios: agrega 3 columnas de auditoria para
--    reclasificacion (linea_aidu_anterior, reclasificacion_fecha,
--    reclasificacion_motivo). NULL para items que no se reclasifiquen.
--
-- 2) Re-puebla aidu_servicios_keywords WHERE tipo=aidu_fast con 6 filas
--    (Ferreteria, Aseo, Oficina, Equipamiento, Salud, Materiales de
--    Construccion). Usa keywords_excluyentes (columna existente desde
--    mig 001 pero hasta ahora no leida por el categorizador).
--
-- Idempotente: DELETE + INSERT OR REPLACE. Re-ejecutar produce mismo estado.

-- 1. Columnas de auditoria
ALTER TABLE inteligencia_precios ADD COLUMN linea_aidu_anterior TEXT;
ALTER TABLE inteligencia_precios ADD COLUMN reclasificacion_fecha TEXT;
ALTER TABLE inteligencia_precios ADD COLUMN reclasificacion_motivo TEXT;

-- 2. Limpiar y re-poblar aidu_fast con 6 lineas (mismo patron que mig 010)
DELETE FROM aidu_servicios_keywords WHERE tipo = 'aidu_fast';

INSERT OR REPLACE INTO aidu_servicios_keywords
    (cod_servicio, nombre, keywords, keywords_excluyentes,
     hh_estimado_ignacio, hh_estimado_jorella, tipo)
VALUES
    ('FAST-FERRETERIA', 'Ferreteria y Construccion (AIDU Fast)', 'cemento,hormigon,fierro,acero,perfil,clavo,tornillo,tuerca,perno,alambre,martillo,taladro,sierra,llave,destornillador,pintura,brocha,rodillo,madera,tabla,ladrillo,bloque,fragüe,yeso,malla,cable,enchufe,interruptor,tuberia,fitting,codo,cañeria,valvula,manguera,herramienta,andamio,escalera,casco,guante,bota,cinta metrica,carretilla,saco arena,gravilla,bisagra,candado,silicona,sellador,pegamento construccion,construccion,iluminacion,luminaria,led,arido,alcantarillado,mejoramiento', '', 0, 0, 'aidu_fast'),
    ('FAST-ASEO', 'Aseo (AIDU Fast)', 'detergente,jabon,cloro,desinfectante,limpiador,escobillon,escoba,trapero,mopa,paño,papel higienico,toalla,servilleta,bolsa basura,dispensador,sanitizante,alcohol gel,lavaloza,suavizante,cera,lustramuebles,ambientador,desodorante,insecticida,desratizador,balde,esponja,guante latex,mascarilla,papel toalla,contenedor,pala,sopapo,limpia vidrios,antibacterial,desincrustante,virutilla,detergente liquido,toalla nova,bolsa basura industrial,alcohol isopropilico,materiales aseo,materiales y articulos de aseo,lavado,planchado', '', 0, 0, 'aidu_fast'),
    ('FAST-OFICINA', 'Oficina (AIDU Fast)', 'papel,resma,hoja,cuaderno,libreta,lapiz,lapicera,boligrafo,plumon,marcador,corrector,goma,sacapunta,regla,tijera,pegamento,cinta adhesiva,archivador,carpeta,separador,folder,sobre,etiqueta,post-it,perforadora,corchetera,corchete,clip,chinche,cartulina,block,agenda,calendario,tinta,toner,cartucho,resaltador,libro acta,papeleria,utiles escritorio,pendon,impresion logos,materiales de oficina', '', 0, 0, 'aidu_fast'),
    ('FAST-EQUIPAMIENTO', 'Equipamiento (AIDU Fast)', 'computador,notebook,laptop,monitor,teclado,mouse,impresora,escaner,proyector,pantalla,escritorio,silla,mesa,estante,mueble,archivador metalico,lockers,refrigerador,microondas,hervidor,cafetera,ventilador,calefactor,aire acondicionado,televisor,telefono,central telefonica,ups,regulador,switch,router,disco duro,memoria ram,procesador,tablet,kardex,estanteria,mueble oficina,computacional,computacion,audio,amplificacion,mobiliario,generador', '', 0, 0, 'aidu_fast'),
    ('FAST-SALUD', 'Salud (AIDU Fast)', 'cateter,sonda,pinza,brazalete,jeringa,gasa,mascarilla quirurgica,sujetador tubo,vendaje,suero,aposito,tubo endotraqueal,endotraqueal,sonda nasogastrica,gastrico,biopsia,grapadora endoscopica,instrumental quirurgico,estetoscopio,tensiometro,oxigeno,electrocardiogr,pulsioximetro,nebulizador,infusion intravenosa,parche curativo,compresa medica,antiseptico,reactivo laboratorio,medicamento,farmaceutico,enfermeria,tecnico de enfermeria,hemostatico,laparoscopica,ecg,monitor signos vitales', 'alcohol gel para uso de oficina', 0, 0, 'aidu_fast'),
    ('FAST-CONSTRUCCION', 'Materiales de Construccion (AIDU Fast)', 'cemento,hormigon,fierro estructural,acero estructural,perfil estructural,viga,pilar,malla acma,enfierradura,arena,gravilla,ripio,arido,base estabilizada,madera dimensionada,terciado,osb,mdf estructural,ladrillo,bloque de hormigon,estuco,mortero,adoquin,yeso carton,volcanita,ceramica para piso,porcelanato,frague,baldosa,plancha zinc,plancha cubierta,fieltro asfaltico,lana mineral,poliestireno expandido,asfalto,pavimento de hormigon', 'pintura de oficina,cemento dental,cemento oseo', 0, 0, 'aidu_fast');
