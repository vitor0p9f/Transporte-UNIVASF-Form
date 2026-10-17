"""Which proposals collide: shared point or shared OD pair."""

from algorithms.top_univasf.model import ConflictKey


def conflict_groups(key_lists: list[list[ConflictKey]]) -> list[list[int]]:
    """Agrupa índices que compartilham alguma chave (união por transitividade).

    Propostas sem chave em comum comitam juntas na mesma rodada; de cada
    grupo em conflito, só a de maior score age.
    """
    parent = list(range(len(key_lists)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict[ConflictKey, int] = {}
    for idx, keys in enumerate(key_lists):
        for key in keys:
            if key in owner:
                a, b = find(idx), find(owner[key])
                if a != b:
                    parent[a] = b
            else:
                owner[key] = idx

    groups: dict[int, list[int]] = {}
    for idx in range(len(key_lists)):
        groups.setdefault(find(idx), []).append(idx)
    return list(groups.values())
