create schema if not exists prata;

create or replace view prata.livros as
with bronze_limpa as (
    select
        btrim(payload->>'upc', E' \t\r\n') as upc, -- R7
        btrim(payload->>'titulo', E' \t\r\n') as titulo, -- R7
        btrim(payload->>'categoria_raw', E' \t\r\n') as categoria_limpa, -- R7
        btrim(payload->>'url', E' \t\r\n') as url, -- R7
        payload,
        id,
        _ingestao_em
    from bronze.livros
)
select distinct on (upc) -- R1
    upc,
    titulo,
    case
        when categoria_limpa in ('Default', 'Add a comment') then 'Sem categoria' -- R6
        else categoria_limpa -- R6
    end as categoria,
    substring(payload->>'preco_raw' from '[0-9]+(?:\.[0-9]+)?')::numeric(10,2) as preco_gbp, -- R2
    case payload->>'rating_raw'
        when 'star-rating One' then 1 -- R3
        when 'star-rating Two' then 2 -- R3
        when 'star-rating Three' then 3 -- R3
        when 'star-rating Four' then 4 -- R3
        when 'star-rating Five' then 5 -- R3
    end as rating,
    coalesce(substring(payload->>'estoque_raw' from '[0-9]+')::int, 0) as estoque_qtd, -- R4
    (payload->>'n_reviews_raw')::int as n_reviews, -- R5
    url,
    _ingestao_em
from bronze_limpa
order by upc, _ingestao_em desc, id desc; -- R1
