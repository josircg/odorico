-- Estudo do OpenAlex x Scopus x Google Scholar

-- quantos registros com google_code mas sem oalex_code
select count(*) from qualis_periodico
 where google_code is not null and oalex_code is null and status = 'A' and qualis != 'ND';

select nome, issn, eissn, google_code, keywords from qualis_periodico
 where google_code is not null and oalex_code is null and status = 'A' and qualis != 'ND';

select nome, issn, eissn, google_code, keywords from qualis_periodico
 where google_code is not null and oalex_code is null and status = 'A' and qualis != 'ND' and area_id is not null;

-- total de períodicos no qualis: 35679
select count(*) from qualis_periodico where status = 'A' and qualis != 'ND';

-- 6891 não estão em nenhum deles (20%)
select count(*) from qualis_periodico
 where oalex_code is null and scopus_code is null and google_code is null and status = 'A' and qualis != 'ND';

select count(*) from qualis_periodico
 where scopus_code is not null and oalex_code is null and status = 'A' and qualis != 'ND';

-- e em relação ao acesso aberto
update qualis_periodico set modelo_economico = null where modelo_economico = 'U';

select modelo_economico,count(*) from qualis_periodico
 where status = 'A' and qualis != 'ND'
group by modelo_economico;


select * from qualis_periodico where google_code is not null and oalex_code is null
  and status = 'A'  and qualis != 'ND';

select * from qualis_periodico where google_code is not null and oalex_code is null and status = 'A';
select count(*) from qualis_periodico where scopus_code is not null and oalex_code is null and status = 'A';

select * from qualis_periodico where pais is null and status = 'A';

select count(*) from qualis_periodico
 where oalex_code is null and scopus_code is not null and qualis != 'ND' and status = 'A';

-- Fixes
update qualis_periodicoindicador set periodico_id = 40229 where periodico_id = 111;

select count(*) from qualis_periodico where status in ('I','F') and dtupdate > '2026-01-01';
select * from qualis_periodico where status in ('I','F') and dtupdate > '2026-04-26';

-- Ajuste do erro no PortalISSN que indicou como inativo mas estava como provisionado
select issn, nome, historico, dtvalidacao, dtupdate from qualis_periodico where status in ('I','F')  and dtupdate > '2026-01-01';

select issn, nome, historico, dtvalidacao from qualis_periodico where status = 'F' and historico = 'Removido do ISSN';
select * from qualis_periodico where status = 'F' and historico = 'ISSN Inválido';

delete from qualis_periodicoissn where issn = '0000-0000';

-- encontrando duplicados - 1202!
select issn, count(distinct periodico_id) from qualis_periodicoissn
 group by issn having count(distinct periodico_id) > 1;

select id,issn,eissn from qualis_periodico where status = 'D';

select * from qualis_periodicoissn where meio = 'D';
update qualis_periodicoissn set meio = 'D' where periodico_id in (select id from qualis_periodico where status = 'D');
select * from qualis_periodicoissn where id = 55303;
select * from qualis_periodicoissn where issn = '0005-9080';

update qualis_periodico set status = 'D' where issn = '0037-7996';
update qualis_periodicoissn set meio = 'D' where periodico_id in (select id from qualis_periodico where issn = '0037-7996');
delete from qualis_periodicoissn where issn in ('2573-5845','2576-7798');

select issn, eissn, status from qualis_periodico where issn in ('0069-9667');
select * from qualis_periodicoissn where periodico_id = 37752;