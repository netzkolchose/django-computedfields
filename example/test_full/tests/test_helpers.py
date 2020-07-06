from django.test import TestCase
from .. import models
from computedfields.helper import is_sublist


class TestHelpers(TestCase):
    def test_is_sublist(self):
        haystack = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        needles_good = [
          [1],
          [1, 2, 3],
          [10],
          [8, 9, 10],
          [2, 3],
          [6, 7, 8]
        ]
        needles_bad = [
          [1, 3],
          [3, 2],
          [0, 1, 2],
          [9, 10, 11],
          [12]
        ]
        for needle in needles_good:
            self.assertEqual(is_sublist(needle, haystack), True)
        for needle in needles_bad:
            self.assertEqual(is_sublist(needle, haystack), False)

        # empty needle is always true
        self.assertEqual(is_sublist([], haystack), True)
        self.assertEqual(is_sublist([], []), True)

        # empty haystack is always false (except for empty needle)
        for needle in needles_good:
            self.assertEqual(is_sublist(needle, []), False)
        for needle in needles_good:
            self.assertEqual(is_sublist(needle, []), False)
