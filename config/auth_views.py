from django.contrib.auth import authenticate, login, logout
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, inline_serializer


class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)


class UserProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField(read_only=True)
    user = UserProfileSerializer(read_only=True)


class LoginView(APIView):
    """
    Authenticate an administrator user and issue an API authentication token as well as a session cookie.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        request=LoginRequestSerializer,
        responses={
            200: LoginResponseSerializer,
            400: inline_serializer(
                name='LoginErrorResponse',
                fields={'detail': serializers.CharField()}
            ),
            403: inline_serializer(
                name='ForbiddenAdminResponse',
                fields={'detail': serializers.CharField()}
            ),
        },
        description="Authenticate with username and password to receive an auth token and establish a session."
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']

        user = authenticate(request=request, username=username, password=password)
        if not user:
            return Response(
                {"detail": "Invalid credentials provided."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not (user.is_staff or user.is_superuser):
            return Response(
                {"detail": "Administrator access required. Only staff accounts may log in."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Establish session for session-based auth
        login(request, user)

        # Retrieve or create auth token for token-based auth
        token, _ = Token.objects.get_or_create(user=user)

        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
        }

        return Response({
            'token': token.key,
            'user': user_data,
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    Log out the currently authenticated administrator. Revokes the authentication token and clears the session.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: inline_serializer(
                name='LogoutResponse',
                fields={'detail': serializers.CharField()}
            )
        },
        description="Log out the current user and revoke their token."
    )
    def post(self, request):
        if hasattr(request, 'auth') and isinstance(request.auth, Token):
            request.auth.delete()

        logout(request)
        return Response(
            {"detail": "Successfully logged out."},
            status=status.HTTP_200_OK
        )


class CurrentUserView(APIView):
    """
    Retrieve profile details of the currently authenticated administrator.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: UserProfileSerializer},
        description="Retrieve information about the currently authenticated user."
    )
    def get(self, request):
        user = request.user
        serializer = UserProfileSerializer({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
        })
        return Response(serializer.data, status=status.HTTP_200_OK)
