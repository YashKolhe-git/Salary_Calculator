from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


class AuthAndDocsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username='adminuser',
            password='adminpassword123',
            email='admin@example.com',
            is_staff=True,
            is_superuser=True
        )
        self.regular_user = User.objects.create_user(
            username='regularuser',
            password='regularpassword123',
            email='worker@example.com',
            is_staff=False
        )

    def test_admin_login_success(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'adminuser',
            'password': 'adminpassword123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['username'], 'adminuser')
        self.assertTrue(response.data['user']['is_staff'])

    def test_non_staff_login_rejected(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'regularuser',
            'password': 'regularpassword123'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Administrator access required', response.data['detail'])

    def test_invalid_credentials_rejected(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'adminuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_current_user_profile(self):
        # Unauthenticated
        resp = self.client.get('/api/auth/me/')
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # Authenticated
        self.client.force_authenticate(user=self.admin_user)
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['username'], 'adminuser')
        self.assertEqual(resp.data['email'], 'admin@example.com')

    def test_logout(self):
        token = Token.objects.create(user=self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        response = self.client.post('/api/auth/logout/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Token should be revoked
        self.assertFalse(Token.objects.filter(key=token.key).exists())

    def test_openapi_schema_endpoint(self):
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_swagger_and_redoc_endpoints(self):
        # When unauthenticated or authenticated
        resp_swagger = self.client.get('/api/docs/')
        self.assertEqual(resp_swagger.status_code, status.HTTP_200_OK)

        resp_redoc = self.client.get('/api/redoc/')
        self.assertEqual(resp_redoc.status_code, status.HTTP_200_OK)
