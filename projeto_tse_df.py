import csv
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_CSV = os.path.join(PASTA_PROJETO, "votacao_candidato_munzona_2026_DF.csv")
QUANTIDADE_TRABALHADORES = min(4, os.cpu_count() or 1)


def carregar_dados(caminho):
    """Lê o CSV e prepara somente os campos necessários ao trabalho."""
    dados = []

    with open(caminho, "r", encoding="latin-1", newline="") as arquivo:
        leitor = csv.DictReader(arquivo, delimiter=";", quotechar='"')

        campos_necessarios = {
            "SG_UF",
            "NM_MUNICIPIO",
            "SG_PARTIDO",
            "DS_CARGO",
            "QT_VOTOS_NOMINAIS_VALIDOS",
        }

        if not campos_necessarios.issubset(set(leitor.fieldnames or [])):
            raise ValueError("O CSV não possui todos os campos esperados.")

        for linha in leitor:
            # Garante que a análise seja somente do Distrito Federal.
            if linha["SG_UF"].strip() != "DF":
                continue

            valor = linha["QT_VOTOS_NOMINAIS_VALIDOS"].strip()

            # O manual do TSE identifica -1 e -3 como códigos especiais.
            # Eles não são quantidades de votos e, portanto, são ignorados.
            if valor in ("", "#NULO", "#NE", "-1", "-3"):
                continue

            votos = int(valor)

            # Zero é um valor válido e deve ser mantido.
            partido = linha["SG_PARTIDO"].strip()
            cargo = linha["DS_CARGO"].strip()

            dados.append((votos, partido, cargo))

    if not dados:
        raise ValueError("Nenhum registro válido do DF foi encontrado.")

    return dados


def dividir_em_partes(dados, quantidade):
    """Divide os registros em partes para distribuir entre trabalhadores."""
    quantidade = max(1, min(quantidade, len(dados)))
    return [dados[i::quantidade] for i in range(quantidade)]


def processar_parte(parte):
    """
    Calcula soma e quantidade de registros.
    Retorna também soma e quantidade por partido e por cargo.
    """
    soma_geral = 0
    quantidade_geral = 0
    partidos = defaultdict(lambda: [0, 0])
    cargos = defaultdict(lambda: [0, 0])

    for votos, partido, cargo in parte:
        soma_geral += votos
        quantidade_geral += 1

        if partido:
            partidos[partido][0] += votos
            partidos[partido][1] += 1

        if cargo:
            cargos[cargo][0] += votos
            cargos[cargo][1] += 1

    return soma_geral, quantidade_geral, dict(partidos), dict(cargos)


def combinar_resultados(resultados_parciais):
    """Combina as somas e contagens de todas as partes."""
    soma_geral = 0
    quantidade_geral = 0
    partidos = defaultdict(lambda: [0, 0])
    cargos = defaultdict(lambda: [0, 0])

    for soma, quantidade, partidos_parciais, cargos_parciais in resultados_parciais:
        soma_geral += soma
        quantidade_geral += quantidade

        for nome, (soma_p, qtd_p) in partidos_parciais.items():
            partidos[nome][0] += soma_p
            partidos[nome][1] += qtd_p

        for nome, (soma_c, qtd_c) in cargos_parciais.items():
            cargos[nome][0] += soma_c
            cargos[nome][1] += qtd_c

    return soma_geral, quantidade_geral, dict(partidos), dict(cargos)


def executar_multithreading(partes):
    """Executa a agregação usando múltiplas threads."""
    with ThreadPoolExecutor(max_workers=len(partes)) as executor:
        parciais = list(executor.map(processar_parte, partes))

    return combinar_resultados(parciais)


def executar_multiprocessing(partes):
    """Executa a agregação usando múltiplos processos."""
    with ProcessPoolExecutor(max_workers=len(partes)) as executor:
        parciais = list(executor.map(processar_parte, partes))

    return combinar_resultados(parciais)


def calcular_medias(agrupamento):
    """Transforma soma/quantidade em média para cada chave."""
    medias = []
    for nome, (soma, quantidade) in agrupamento.items():
        medias.append((nome, soma / quantidade, soma, quantidade))

    return sorted(medias, key=lambda item: item[1], reverse=True)



def imprimir_resultados(titulo, resultado):
    soma, quantidade, partidos, cargos = resultado

    # Painel de resumo
    resumo = Table.grid(padding=(0, 3))
    resumo.add_column(style="bold cyan")
    resumo.add_column(style="bold white", justify="right")

    resumo.add_row("Registros analisados", f"{quantidade:,}".replace(",", "."))
    resumo.add_row("Soma dos votos", f"{soma:,}".replace(",", "."))
    resumo.add_row(
        "Média geral",
        f"{soma / quantidade:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )

    console.print()
    console.print(
        Panel(
            resumo,
            title="[bold cyan]ANÁLISE ELEITORAL · TSE 2026[/bold cyan]",
            subtitle="[dim]DISTRITO FEDERAL[/dim]",
            border_style="bright_blue",
            padding=(1, 3)
        )
    )

    # Tabela de partidos
    tabela_partidos = Table(
        title="MÉDIA POR PARTIDO",
        header_style="bold cyan",
        border_style="bright_blue"
    )

    tabela_partidos.add_column("Partido", style="white")
    tabela_partidos.add_column("Média", justify="right", style="green")
    tabela_partidos.add_column("Registros", justify="right")

    medias_partidos = calcular_medias(partidos)

    for nome, media, soma_p, qtd_p in medias_partidos:
        valor = f"{media:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        tabela_partidos.add_row(nome, valor, str(qtd_p))

    console.print(tabela_partidos)

    # Tabela de cargos
    tabela_cargos = Table(
        title="MÉDIA POR CARGO",
        header_style="bold cyan",
        border_style="bright_blue"
    )

    tabela_cargos.add_column("Cargo", style="white")
    tabela_cargos.add_column("Média", justify="right", style="green")
    tabela_cargos.add_column("Registros", justify="right")

    medias_cargos = calcular_medias(cargos)

    for nome, media, soma_c, qtd_c in medias_cargos:
        valor = f"{media:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        tabela_cargos.add_row(nome, valor, str(qtd_c))

    console.print(tabela_cargos)

    # Destaques
    destaques = (
        f"[bold green]Maior média por partido:[/bold green] "
        f"{medias_partidos[0][0]} ({medias_partidos[0][1]:.2f})\n"
        f"[bold green]Maior média por cargo:[/bold green] "
        f"{medias_cargos[0][0]} ({medias_cargos[0][1]:.2f})"
    )

    console.print(
        Panel(destaques, title="DESTAQUES", border_style="green")
    )

def main():
    inicio_leitura = time.perf_counter()
    dados = carregar_dados(ARQUIVO_CSV)
    tempo_leitura = time.perf_counter() - inicio_leitura

    partes = dividir_em_partes(dados, QUANTIDADE_TRABALHADORES)

    print(f"Arquivo analisado: {ARQUIVO_CSV}")
    print(f"Registros carregados: {len(dados):,}".replace(",", "."))
    print(f"Quantidade de trabalhadores: {len(partes)}")
    print(f"Tempo de leitura/preparação comum: {tempo_leitura:.6f} segundos")

    inicio = time.perf_counter()
    resultado_threads = executar_multithreading(partes)
    tempo_threads = time.perf_counter() - inicio

    inicio = time.perf_counter()
    resultado_processos = executar_multiprocessing(partes)
    tempo_processos = time.perf_counter() - inicio

    # Verifica se os dois métodos produziram exatamente os mesmos agregados.
    if resultado_threads != resultado_processos:
        raise RuntimeError("Os resultados dos métodos não são iguais.")

    imprimir_resultados("ANÁLISE DOS DADOS", resultado_threads)

    
    # Tabela de comparação de desempenho
    tabela_tempo = Table(
        title="COMPARAÇÃO DE DESEMPENHO",
        header_style="bold cyan",
        border_style="bright_blue"
    )

    tabela_tempo.add_column("Método", style="white")
    tabela_tempo.add_column("Tempo (segundos)", justify="right")
    
    tabela_tempo.add_row("Multithreading", f"{tempo_threads:.6f}")
    tabela_tempo.add_row("Multiprocessing", f"{tempo_processos:.6f}")

    console.print()
    console.print(tabela_tempo)

    if tempo_threads < tempo_processos:
        mais_rapido = "MULTITHREADING"
    elif tempo_processos < tempo_threads:
        mais_rapido = "MULTIPROCESSING"
    else:
        mais_rapido = "EMPATE"

    console.print(
        Panel(
            f"[bold green]Mais rápido nesta execução: {mais_rapido}[/bold green]",
            border_style="green"
        )
    )

    console.print("[dim]Os tempos podem variar conforme o computador e a execução.[/dim]")

    if tempo_threads < tempo_processos:
        print("Mais rápido nesta execução: MULTITHREADING")
    elif tempo_processos < tempo_threads:
        print("Mais rápido nesta execução: MULTIPROCESSING")
    else:
        print("Os dois métodos tiveram o mesmo tempo nesta execução.")

    print("\\nOs tempos podem variar conforme o computador e a execução.")


if __name__ == "__main__":
    main()
