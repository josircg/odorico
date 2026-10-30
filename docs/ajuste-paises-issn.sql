-- A base do ISSN grava erradamente o nome dos estados anglosaxões ao invés de utilizar o nome do país
-- dessa forma, é necessário corrigir a base após uma importação que utilize o ISSN como fonte de dados

select distinct pais from qualis_periodico order by 1;

update qualis_periodico set pais = 'USA' where pais in (
'United states', 'Arizona','Delaware','Indiana','Rhode island','Oregon','Oklahoma', 'Massachusetts', 'Virginia',
'Ohio','Missouri','Maryland','Nebraska','Alabama','Tennessee','Kentucky', 'North carolina', 'Arkansas', 'Texas',
'Maine','Mississippi','Minnesota','Kansas','Colorado','Nevada','Hawaii','Louisiana', 'Michigan',
'New hampshire','Iowa','Utah','New mexico','Montana','West virginia','Wyoming','South carolina','North dakota',
'Idaho','New york (state)','Vermont', 'Alaska', 'South dakota', 'Illinois', 'New jersey', 'California',
'District of columbia','EUA','Florida','Connecticut', 'Washington (state)', 'Pennsylvania');

update qualis_periodico set pais = 'Canada'
 where pais in ('Nova scotia','British columbia','New brunswick','Manitoba','Saskatchewan',
                'Newfoundland and labrador', 'Prince edward island','Nunavut', 'Ontario',
                'Québec (province)');

update qualis_periodico set pais = 'Australia'
 where pais in ('New south wales','Victoria','Western australia','South australia',
                'Alberta','Queensland', 'Tasmania', 'Northern territory');

select distinct pais from qualis_periodico where pais like '%Taiwan%';
update qualis_periodico set pais = 'China' where pais like '%Hong Kong%';
update qualis_periodico set pais = 'China' where pais = 'China (republic : 1949- )';

select distinct pais from qualis_periodico where pais like '%korea%';
update qualis_periodico set pais = 'South Korea' where pais = 'Korea (south)';
update qualis_periodico set pais = 'South Korea' where pais = 'Korea (republic of)';
update qualis_periodico set pais = 'North Korea' where pais = 'Korea (north)';

select distinct pais from qualis_periodico where pais like '%Iran%';
update qualis_periodico set pais = 'Iran' where pais = 'Iran (islamic republic of)';

select distinct pais from qualis_periodico where pais like '%Viet%';
update qualis_periodico set pais = 'Vietnam' where pais = 'Viet Nam';

update qualis_periodico set pais = 'Russia' where pais = 'Russian Federation';
update qualis_periodico set pais = 'Russia' where pais = 'Russia (federation)';
update qualis_periodico set pais = 'United kingdom' where pais = 'England';

select pais, count(*) from qualis_periodico where status = 'A'
 group by pais order by 2 desc;
