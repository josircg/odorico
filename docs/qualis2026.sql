select modelo_economico, count(*) from qualis_periodico where status = 'A' and qualis != 'ND'
group by 1;

update qualis_periodico set eissn = null where issn = eissn;

-- Distribuição geral
select qualis, count(*) from qualis_periodico
where status = 'A'
group by qualis;

-- Total de Periódicos com Qualis: 35.679
select count(*) from qualis_periodico where qualis != 'ND' and status = 'A';

select count(*) from qualis_periodico where qualis != 'ND' and pais != 'Brazil';

-- Total em 2024: 27.119
select count(*) from qualis_periodico where qualis_ant != 'ND';
select count(*) from qualis_periodico where qualis_ant != 'ND' and pais != 'Brazil';

-- total de novos periódicos (875)
select count(*) from qualis_periodico where id > 155661 and qualis != 'ND' and status = 'A';

select qualis_ant, count(*) from qualis_periodico
where status = 'A'
group by qualis_ant;

-- Distribuição dos novos periódicos
select qualis, count(*) from qualis_periodico
where id > 155661 and qualis != 'ND'
group by qualis;

-- Qualis sem país (238)
select count(*) from qualis_periodico where qualis != 'ND' and pais is null;

select id, issn, nome, url from qualis_periodico where qualis != 'ND' and pais is null;

select status, count(*) from qualis_periodico
 where qualis != 'ND'
group by 1
order by 2 desc;

update qualis_periodico set modelo_economico = 'A' where modelo_economico = 'P';

-- Por modelo econômico (T-15172, A-3730, D-5794)
select modelo_economico, count(*) from qualis_periodico
where qualis != 'ND' and status = 'A'
group by 1
order by 2 desc;

-- Por modelo econômico (T-15172, A-3731, D-5799)
-- Total: 35677
-- 30,76% não foram qualificados
select modelo_economico, count(*) from qualis_periodico
where qualis != 'ND' and status = 'A'
group by 1
order by 2 desc;

select * from qualis_periodico where modelo_economico is null and status = 'A';

select * from qualis_periodico where issn = '0254-2129';
select * from qualis_periodicoissn where issn = '0254-2129';
select * from qualis_periodico where nome = 'MUSEUM HISTORY JOURNAL';

-- Comparação entre o Qualis Novo e o Qualis Antigo (16586)
-- Quantos cairam: 4266
select count(*) from qualis_periodico
where qualis > qualis_ant and qualis != 'ND' and qualis_ant != 'ND' and status='A';

-- 7607 subiram
select count(*) from qualis_periodico
where qualis < qualis_ant and qualis != 'ND' and qualis_ant != 'ND' and status = 'A';

select modelo_economico, count(*) from qualis_periodico
where qualis < qualis_ant and qualis != 'ND' and qualis_ant != 'ND' and status = 'A'
group by 1;

select modelo_economico, count(*) from qualis_periodico
where qualis < qualis_ant and qualis != 'ND' and qualis_ant != 'ND' and status = 'A'
group by 1;

-- quantos existiam antes e depois
select * from
(select modelo_economico, count(*) qualis_ant from qualis_periodico
where qualis_ant != 'ND' and status = 'A' and area_id in (1,2,3,9)
group by 1
order by 2 desc) ant,
(select modelo_economico, count(*) qualis from qualis_periodico
where qualis != 'ND' and status = 'A' and area_id in (1,2,3,9)
group by 1
order by 2 desc) novo
where ant.modelo_economico = novo.modelo_economico;

-- mas houve melhora nos estratos
select * from
(select modelo_economico, count(*) qualis_ant from qualis_periodico
where qualis_ant != 'ND' and status = 'A' and area_id in (1,2,3,9)
group by 1
order by 2 desc) ant,
(select modelo_economico, count(*) qualis from qualis_periodico
where qualis != 'ND' and status = 'A' and area_id in (1,2,3,9)
group by 1
order by 2 desc) novo
where ant.modelo_economico = novo.modelo_economico;

select modelo_economico, count(*) from qualis_periodico
where qualis < qualis_ant and qualis != 'ND' and qualis_ant != 'ND' and status = 'A'
group by 1
order by 2 desc;

-- E específicos para Ciência da Informação
-- D-81, T-59, A-3
select modelo_economico, count(*) from qualis_periodico
where qualis != 'ND' and status = 'A' and area_id = 2
group by 1
order by 2 desc;

select count(*) from qualis_periodico
where status = 'A' and area_id = 2;

-- Quantos países registrados
select pais, count(*) from qualis_periodico
 where qualis != 'ND' # and status = 'A'
group by pais
order by 2 desc;

-- quais os países que mais subiram
select pais, count(*) from qualis_periodico
where qualis < qualis_ant and qualis != 'ND' and qualis_ant != 'ND' and status='A'
group by pais
order by 2 desc;

