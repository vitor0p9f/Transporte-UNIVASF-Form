# Levantamento de Transporte Universitário — UNIVASF 2026.1

Formulário web para coleta de dados sobre a utilização do transporte estudantil da UNIVASF no primeiro semestre de 2026. Os dados visam subsidiar uma pesquisa acadêmica sobre superlotação nos transportes universitários.

---

## 📋 Sobre o projeto

O formulário permite que estudantes registrem as viagens que realizam no transporte universitário, informando turno, ponto de embarque, ponto de desembarque e nível de lotação percebido. Os dados coletados serão utilizados para análise e proposição de soluções para os problemas de superlotação.

---

## ✨ Funcionalidades

- **Registro de múltiplas viagens** — o usuário pode adicionar até 3 viagens por resposta (uma por turno: manhã, tarde e noite)
- **Prevenção de duplicatas** — cada turno só pode ser selecionado uma vez; opções já utilizadas ficam desabilitadas nos demais cartões
- **Escala de lotação** — avaliação de 1 a 5, de "há poltronas vagas" a "muitas pessoas em pé"
- **Validação antes do envio** — todos os campos são obrigatórios; um alerta é exibido caso algum esteja incompleto
- **Feedback de sucesso** — mensagem de confirmação exibida após o envio
- **Layout responsivo** — adapta-se a telas menores (mobile-first)

---

## 🗂️ Estrutura do formulário

Cada viagem registrada contém os seguintes campos:

| Campo | Tipo | Descrição |
|---|---|---|
| **Turno** | Select | Manhã, Tarde ou Noite |
| **Embarque** | Select | Ponto de origem da viagem |
| **Desembarque** | Select | Ponto de destino da viagem |
| **Lotação** | Radio (1–5) | Nível de ocupação percebido no ônibus |

---

## 🚀 Como usar

Por ser um arquivo HTML único e sem dependências de servidor, basta abrir o arquivo no navegador:

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/levantamento-transporte-univasf.git

# Abra o arquivo no navegador
open levantamento-transporte-univasf.html
```

> Não é necessário instalar nada. O formulário funciona completamente no lado do cliente (front-end only).

---

## 🛠️ Tecnologias

- **HTML5** — estrutura da página
- **CSS3** — estilização com variáveis CSS e layout em grid
- **JavaScript (Vanilla)** — lógica de renderização dinâmica e validação
- **Google Fonts** — tipografia DM Sans e DM Mono
