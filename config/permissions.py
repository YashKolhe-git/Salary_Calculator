from rest_framework.permissions import BasePermission


class IsAuthenticatedAdmin(BasePermission):
    """
    Allows access only to authenticated administrator users (is_staff=True or is_superuser=True).
    Denies access to anonymous users and regular non-staff users.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.is_superuser)
        )
