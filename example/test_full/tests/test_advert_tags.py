from django.test import TestCase
from .. import models


class TestAdvertTags(TestCase):
    def test(self):
        tag_1 = models.Tag.objects.create(name="T1")
        tag_2 = models.Tag.objects.create(name="T2")
        assert models.run_counter == 0
        advert_1 = models.Advert.objects.create(name="A1")
        assert models.run_counter == 1, f"advert.run_counter={models.run_counter}"
        advert_1.tags.add(tag_1)
        assert models.run_counter == 2, f"advert.run_counter={models.run_counter}"
        advert_2 = models.Advert.objects.create(name="A2")
        assert models.run_counter == 3, f"advert.run_counter={models.run_counter}"
        advert_1.tags.set([tag_2])
        assert models.run_counter == 4, f"advert.run_counter={models.run_counter}"
