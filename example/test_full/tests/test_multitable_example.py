from django.test import TestCase
from ..models import User, EmailUser, Work


class TestUserMultiTable(TestCase):
    def setUp(self):
        self.normal_user = User.objects.create(forname='John', surname='Doe')
        self.email_user = EmailUser.objects.create(forname='Sally', surname='Housecoat', email='s.h@example.com')
        self.work1 = Work.objects.create(subject='close window', user=self.normal_user)
        self.work2 = Work.objects.create(subject='open door', user=self.email_user)

    def test_initial(self):
        # working on local fields should correctly update all fields including those on parent models
        self.assertEqual(self.normal_user.fullname, 'Doe, John')
        self.assertEqual(self.email_user.fullname, 'Housecoat, Sally')
        self.assertEqual(self.email_user.email_contact, 'Housecoat, Sally <s.h@example.com>')
        self.assertEqual(self.work1.descriptive_assigment, '"close window" is assigned to "Doe, John"')
        self.assertEqual(self.work2.descriptive_assigment, '"open door" is assigned to "Housecoat, Sally"')

    def test_change_surname_on_user(self):
        john = User.objects.get(forname='John')
        john.surname = 'Bow'
        john.save(update_fields=['surname'])
        john.refresh_from_db()
        self.assertEqual(john.fullname, 'Bow, John')

        sally = User.objects.get(forname='Sally')
        sally.surname = 'Houseboat'
        sally.save(update_fields=['surname'])
        sally.refresh_from_db()
        self.assertEqual(sally.fullname, 'Houseboat, Sally')
        
        # this only updates .email_contact correctly with ('user_ptr', ['fullname']) in depends
        # (ascending rule to extend EmailUser to User)
        self.email_user.refresh_from_db()
        self.assertEqual(self.email_user.email_contact, 'Houseboat, Sally <s.h@example.com>')

        # this updates correctly since User got updated
        self.work1.refresh_from_db()
        self.assertEqual(self.work1.descriptive_assigment, '"close window" is assigned to "Bow, John"')
        self.work2.refresh_from_db()
        self.assertEqual(self.work2.descriptive_assigment, '"open door" is assigned to "Houseboat, Sally"')

    def test_change_surname_on_emailuser(self):
        sally = EmailUser.objects.get(forname='Sally')
        sally.surname = 'Houseboat'
        sally.save(update_fields=['surname'])

        # this work correctly since .fullname is treated as local field
        sally.refresh_from_db()
        self.assertEqual(sally.fullname, 'Houseboat, Sally')

        # .descriptive_assigment only updates correctly with ('user.emailuser', ['fullname']) in depends
        # (descending rule to extend User to EmailUser)
        self.work2.refresh_from_db()
        self.assertEqual(self.work2.descriptive_assigment, '"open door" is assigned to "Houseboat, Sally"')
