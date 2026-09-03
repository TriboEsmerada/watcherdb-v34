"""
Advanced Fuzzy Matcher
Multiple algorithms: Levenshtein, Jaro-Winkler, Soundex, N-grams
"""

from typing import List, Tuple, Set


class AdvancedFuzzyMatcher:
    """
    Implementacao avancada de fuzzy matching
    Multiplos algoritmos: Levenshtein, Jaro-Winkler, Soundex, N-grams
    """

    @staticmethod
    def levenshtein_distance(s1: str, s2: str) -> int:
        """Distancia de Levenshtein (edit distance)"""
        if len(s1) < len(s2):
            return AdvancedFuzzyMatcher.levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    @staticmethod
    def jaro_winkler_similarity(s1: str, s2: str) -> float:
        """Jaro-Winkler similarity"""
        if not s1 or not s2:
            return 0.0

        if s1 == s2:
            return 1.0

        # Jaro similarity
        match_window = max(len(s1), len(s2)) // 2 - 1
        if match_window < 0:
            match_window = 0

        s1_matches = [False] * len(s1)
        s2_matches = [False] * len(s2)

        matches = 0
        transpositions = 0

        # Find matches
        for i in range(len(s1)):
            start = max(0, i - match_window)
            end = min(i + match_window + 1, len(s2))

            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
                    continue
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

        if matches == 0:
            return 0.0

        # Count transpositions
        k = 0
        for i in range(len(s1)):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1

        jaro = (matches / len(s1) + matches / len(s2) + (matches - transpositions/2) / matches) / 3

        # Winkler modification
        prefix = 0
        for i in range(min(len(s1), len(s2), 4)):
            if s1[i] == s2[i]:
                prefix += 1
            else:
                break

        return jaro + (0.1 * prefix * (1 - jaro))

    @staticmethod
    def soundex(s: str) -> str:
        """Soundex algorithm for phonetic matching"""
        if not s:
            return "0000"

        s = s.upper()
        soundex_map = {
            'BFPV': '1', 'CGJKQSXZ': '2', 'DT': '3',
            'L': '4', 'MN': '5', 'R': '6'
        }

        result = s[0]

        for char in s[1:]:
            for key, value in soundex_map.items():
                if char in key:
                    if value != result[-1]:  # Avoid consecutive duplicates
                        result += value
                    break

            if len(result) == 4:
                break

        return result.ljust(4, '0')[:4]

    @staticmethod
    def n_grams(s: str, n: int = 2) -> Set[str]:
        """Generate n-grams from string"""
        s = s.lower()
        return set(s[i:i+n] for i in range(len(s) - n + 1))

    @staticmethod
    def n_gram_similarity(s1: str, s2: str, n: int = 2) -> float:
        """N-gram similarity"""
        if not s1 or not s2:
            return 0.0

        grams1 = AdvancedFuzzyMatcher.n_grams(s1, n)
        grams2 = AdvancedFuzzyMatcher.n_grams(s2, n)

        if not grams1 and not grams2:
            return 1.0

        intersection = len(grams1 & grams2)
        union = len(grams1 | grams2)

        return intersection / union if union > 0 else 0.0

    @staticmethod
    def combined_similarity(s1: str, s2: str) -> float:
        """Weighted combination of multiple similarity algorithms"""
        if not s1 or not s2:
            return 0.0

        s1, s2 = s1.lower().strip(), s2.lower().strip()

        if s1 == s2:
            return 100.0

        # Exact substring match
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return (shorter / longer) * 95

        # Multiple algorithms
        levenshtein_sim = 1 - (AdvancedFuzzyMatcher.levenshtein_distance(s1, s2) / max(len(s1), len(s2)))
        jaro_winkler_sim = AdvancedFuzzyMatcher.jaro_winkler_similarity(s1, s2)
        ngram_sim = AdvancedFuzzyMatcher.n_gram_similarity(s1, s2)

        # Soundex bonus for phonetic similarity
        soundex_bonus = 0.1 if AdvancedFuzzyMatcher.soundex(s1) == AdvancedFuzzyMatcher.soundex(s2) else 0

        # Weighted average
        combined = (
            levenshtein_sim * 0.3 +
            jaro_winkler_sim * 0.4 +
            ngram_sim * 0.3 +
            soundex_bonus
        )

        return min(100.0, combined * 100)

    @staticmethod
    def extract_best_matches(query: str, choices: List[str], limit: int = 10, threshold: float = 60.0) -> List[Tuple[str, float]]:
        """Extract best matches from choices"""
        if not query or not choices:
            return []

        scores = []
        for choice in choices:
            score = AdvancedFuzzyMatcher.combined_similarity(query, choice)
            if score >= threshold:
                scores.append((choice, score))

        # Sort by score and return top matches
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:limit]
