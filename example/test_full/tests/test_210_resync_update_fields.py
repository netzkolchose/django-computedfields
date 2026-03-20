"""
Test cases for not_computed context manager _resync method update_fields handling.

These tests cover two issues:
1. Case 1: Model with a computed field which is not updated triggers the update of all
   related dependencies when it shouldn't (when using save(update_fields=[...]) with
   fields that don't affect the computed field on a dependent model).

2. Case 2: Update of dependent model not being triggered when it should (when using
   save(update_fields=[...]) with fields that SHOULD trigger a dependent update).
"""
from django.test import TestCase
from ..models import ResyncModelA, ResyncModelB, ResyncModelC, ResyncModelD
from computedfields.models import not_computed


class ResyncUpdateFieldsCase1(TestCase):
    """
    Test Case 1: Model save with update_fields that don't affect M2M dependency field
    should NOT trigger unnecessary updates on related models.

    Setup:
    - ResyncModelA has fields: field_1, field_2, computed_field (depends on field_1, field_2)
    - ResyncModelB has m2m_field to ResyncModelA and computed_field that depends on m2m_field['id']

    When ResyncModelA.save(update_fields=['field_1']) is called inside not_computed context,
    ResyncModelB should NOT be updated because 'field_1' is not in ResyncModelB's depends list
    (it only depends on 'id').
    """

    def setUp(self):
        # Create models outside not_computed context first
        self.model_a = ResyncModelA.objects.create(field_1=10.0, field_2=20.0)
        self.model_b = ResyncModelB.objects.create()
        self.model_b.m2m_field.add(self.model_a)
        self.model_b.refresh_from_db()

    def test_initial_state(self):
        """Verify initial computed field values."""
        self.model_a.refresh_from_db()
        self.model_b.refresh_from_db()

        # ResyncModelA.computed_field = field_1 + field_2 = 10 + 20 = 30
        self.assertEqual(self.model_a.computed_field, 30.0)
        # ResyncModelB.computed_field = count of m2m_field = 1
        self.assertEqual(self.model_b.computed_field, 10)

    def test_update_field_not_in_depends_should_not_trigger_related_update(self):
        """
        When updating a field that is NOT in the depends list of the related model,
        the related model should NOT be recomputed.

        This test verifies that when ResyncModelA.save(update_fields=['field_1']) is
        called, ResyncModelB should NOT be updated because its computed_field only
        depends on ['id'], not on 'field_1'.
        """
        initial_b_computed = self.model_b.computed_field

        with not_computed(recover=True):
            self.model_a.field_1 = 100.0
            self.model_a.save(update_fields=['field_1'])

        self.model_a.refresh_from_db()
        self.model_b.refresh_from_db()

        # ResyncModelA.computed_field should be updated to 100 + 20 = 120
        self.assertEqual(self.model_a.computed_field, 120.0)

        # ResyncModelB.computed_field should remain unchanged (still 1.0)
        # because its depends list only has 'id', not 'field_1'
        self.assertEqual(self.model_b.computed_field, initial_b_computed)


class ResyncUpdateFieldsCase2(TestCase):
    """
    Test Case 2: Model save with update_fields that SHOULD trigger dependent model update.

    Setup:
    - ResyncModelC has field_1 and computed_field (depends on field_1)
    - ResyncModelD has m2m_field to ResyncModelC and computed_field that depends on m2m_field['field_1']

    When ResyncModelC.save(update_fields=['field_1']) is called inside not_computed context,
    ResyncModelD SHOULD be updated because 'field_1' IS in ResyncModelD's depends list.
    """

    def setUp(self):
        # Create models outside not_computed context first
        self.model_c = ResyncModelC.objects.create(field_1=5.0)
        self.model_d = ResyncModelD.objects.create()
        self.model_d.m2m_field.add(self.model_c)
        self.model_d.refresh_from_db()

    def test_initial_state(self):
        """Verify initial computed field values."""
        self.model_c.refresh_from_db()
        self.model_d.refresh_from_db()

        # ResyncModelC.computed_field = field_1 * 2 = 5 * 2 = 10
        self.assertEqual(self.model_c.computed_field, 10.0)
        # ResyncModelD.computed_field = sum of field_1 from m2m = 5
        self.assertEqual(self.model_d.computed_field, 5.0)

    def test_update_field_in_depends_should_trigger_related_update(self):
        """
        When updating a field that IS in the depends list of the related model,
        the related model SHOULD be recomputed.

        This test verifies that when ResyncModelC.save(update_fields=['field_1']) is
        called, ResyncModelD SHOULD be updated because its computed_field depends on
        m2m_field['field_1'].
        """
        with not_computed(recover=True):
            self.model_c.field_1 = 15.0
            self.model_c.save(update_fields=['field_1'])

        self.model_c.refresh_from_db()
        self.model_d.refresh_from_db()

        # ResyncModelC.computed_field should be updated to 15 * 2 = 30
        self.assertEqual(self.model_c.computed_field, 30.0)

        # ResyncModelD.computed_field SHOULD be updated to sum of field_1 = 15
        self.assertEqual(self.model_d.computed_field, 15.0)

    def test_update_with_multiple_related_objects(self):
        """
        Test with multiple related objects to ensure all dependent models are updated.
        """
        # Add another ResyncModelC instance
        model_c2 = ResyncModelC.objects.create(field_1=3.0)
        self.model_d.m2m_field.add(model_c2)
        self.model_d.refresh_from_db()

        # Initial state: model_d.computed_field = 5 + 3 = 8
        self.assertEqual(self.model_d.computed_field, 8.0)

        with not_computed(recover=True):
            self.model_c.field_1 = 20.0
            self.model_c.save(update_fields=['field_1'])

        self.model_d.refresh_from_db()

        # After update: model_d.computed_field should be 20 + 3 = 23
        self.assertEqual(self.model_d.computed_field, 23.0)


class ResyncUpdateFieldsCase2NC(TestCase):
    """
    Same as Case2 but with setup also inside not_computed context.
    """

    def setUp(self):
        with not_computed(recover=True):
            self.model_c = ResyncModelC.objects.create(field_1=5.0)
            self.model_d = ResyncModelD.objects.create()
            self.model_d.m2m_field.add(self.model_c)
        self.model_c.refresh_from_db()
        self.model_d.refresh_from_db()

    def test_initial_state(self):
        """Verify initial computed field values after setup in not_computed context."""
        # ResyncModelC.computed_field = field_1 * 2 = 5 * 2 = 10
        self.assertEqual(self.model_c.computed_field, 10.0)
        # ResyncModelD.computed_field = sum of field_1 from m2m = 5
        self.assertEqual(self.model_d.computed_field, 5.0)

    def test_update_field_in_depends_should_trigger_related_update(self):
        """
        When updating a field that IS in the depends list of the related model,
        the related model SHOULD be recomputed.
        """
        with not_computed(recover=True):
            self.model_c.field_1 = 15.0
            self.model_c.save(update_fields=['field_1'])

        self.model_c.refresh_from_db()
        self.model_d.refresh_from_db()

        # ResyncModelC.computed_field should be updated to 15 * 2 = 30
        self.assertEqual(self.model_c.computed_field, 30.0)

        # ResyncModelD.computed_field SHOULD be updated to sum of field_1 = 15
        self.assertEqual(self.model_d.computed_field, 15.0)
