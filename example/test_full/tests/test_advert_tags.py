from django.test import TestCase
from .. import models


class TestAdvertTags(TestCase):
    def test(self):
        tag_ready = models.Tag.objects.create(name="ready")
        advert_1 = models.Advert.objects.create(name="A1")
        room_11 = models.Room.objects.create(name="R11", advert=advert_1)
        advert_1.tags.add(tag_ready)
        advert_2 = models.Advert.objects.create(name="A2")
        room_21 = models.Room.objects.create(name="R21", advert=advert_2)
        assert models.run_counters["all_tags"] == 3
        assert models.run_counters["is_ready"] == 3

        advert_2.tags.add(tag_ready)
        assert models.run_counters["all_tags"] == 4
        assert models.run_counters["is_ready"] == 4
