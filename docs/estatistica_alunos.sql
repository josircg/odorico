-- ID_CNPQ dos professores e alunos
select p.id_cnpq from nucleo_pesquisadorprograma l, nucleo_pesquisador p
 where l.pesquisador_id = p.id
union
select p.id_cnpq
  from nucleo_matricula m, nucleo_pesquisador p
 where m.pesquisador_id = p.id
   and id_cnpq is not null;

-- estatística de produção dos discentes
select ano, nucleo_tipoproducao.descricao, count(distinct nucleo_producao.ident_unico) total
 from nucleo_producao, nucleo_producaoautor, nucleo_pesquisador, nucleo_matricula m, nucleo_tipoproducao,
      nucleo_curso curso, nucleo_programa programa
where nucleo_producao.id = nucleo_producaoautor.producao_id
  and nucleo_producaoautor.autor_id = m.pesquisador_id
  and tipo_id = nucleo_tipoproducao.id
  and ano > 2018
  and m.curso_id = curso.id
  and curso.programa_id = programa.id
  and programa.descricao = 'Sociologia' -- and curso.nivel = 'ME'
group by 1, 2;

select distinct nucleo_producao.id, nucleo_producao.titulo, ano, nucleo_producao.ident_unico
 from nucleo_producao, nucleo_producaoautor, nucleo_pesquisador, nucleo_matricula, nucleo_tipoproducao
where nucleo_producao.id = nucleo_producaoautor.producao_id
  and nucleo_producaoautor.autor_id = nucleo_matricula.pesquisador_id
  and tipo_id = nucleo_tipoproducao.id
  and ano > 2018
  and tipo_id = 18;

-- listagem das produções de cada discente
select ano, nucleo_tipoproducao.descricao, nucleo_pesquisador.nome, p.*
 from nucleo_producao as p, nucleo_pesquisador, nucleo_tipoproducao,
      (select pesquisador_id, ingresso, c.descricao
         from nucleo_matricula as m, nucleo_curso as c
        where ingresso = (select max(ingresso) from nucleo_matricula as max where max.pesquisador_id = m.pesquisador_id)
          and m.curso_id = c.id) matricula
where p.pesquisador_id = nucleo_pesquisador.id
  and p.tipo_id = nucleo_tipoproducao.id
  and p.pesquisador_id = matricula.pesquisador_id
  and ano > 2018
  and matricula.descricao = 'Mestrado'
order by 1, 2, 3, 4;

-- total de alunos com mais de uma matrícula
select pesquisador_id, count(ingresso)
  from nucleo_matricula
group by pesquisador_id
having count(ingresso) > 1;

select ingresso, c.descricao
  from nucleo_matricula as m, nucleo_curso as c
 where ingresso in (select max(ingresso) from nucleo_matricula as max where max.pesquisador_id = m.pesquisador_id)
   and m.curso_id = c.id and pesquisador_id = 2330;

-- análise dos Identificadores duplicados
select ident_unico, tipo_id, count(*) from nucleo_producao
group by ident_unico, tipo_id
having count(*) > 1

select * from nucleo_producao
 where ident_unico = '00e0189279230706ea0a8cc2bf4508b5';


