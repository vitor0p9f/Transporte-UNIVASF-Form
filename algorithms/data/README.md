# /data

Coloque aqui os arquivos de entrada para os algoritmos.

## Arquivo esperado: `viagens.csv`

Exportado direto do Supabase (Table Editor → Export → CSV).

### Colunas esperadas:

| Coluna       | Tipo    | Descrição                                      |
|--------------|---------|------------------------------------------------|
| `id`         | int     | Identificador único da viagem                  |
| `email`      | string  | E-mail do participante (usado apenas para dedup) |
| `turno`      | string  | Slug do turno (ex: `manha_1`, `tarde_2`)       |
| `embarque`   | string  | Nome da parada de embarque                     |
| `desembarque`| string  | Nome da parada de desembarque                  |
| `lotacao`    | int     | Índice de lotação percebida (1–5)              |
| `created_at` | string  | Timestamp UTC da inserção                      |

### Exemplo de linha:
```
1,joao@discente.univasf.edu.br,manha_1,UNIVASF Campus Juazeiro,UNIVASF Campus Petrolina,3,2026-05-01T10:00:00+00:00
```

> Os arquivos CSV **não são versionados** (estão no .gitignore) pois contêm dados pessoais (e-mail).
