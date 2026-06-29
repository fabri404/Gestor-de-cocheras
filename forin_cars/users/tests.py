"""
Tests de regresión — app users.

Cobertura:
- login / logout (POST requerido para logout)
- registro llama apply_pending_invites
- dashboard: contexto correcto por rol
"""
from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse

from parking.models import Cochera, CocheraEmpleado, InvitacionEmpleado, TipoEspacio
from parking.services import invitar_empleados


def make_group(name):
    g, _ = Group.objects.get_or_create(name=name)
    return g


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("user1", password="pass123")

    def test_login_get_renderiza_form(self):
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)

    def test_login_credenciales_correctas_redirige_dashboard(self):
        resp = self.client.post(reverse("login"), {"username": "user1", "password": "pass123"})
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

    def test_login_credenciales_incorrectas_vuelve_al_form(self):
        resp = self.client.post(reverse("login"), {"username": "user1", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)

    def test_logout_get_no_permitido(self):
        """logout_view requiere POST desde Django best practices."""
        self.client.login(username="user1", password="pass123")
        resp = self.client.get(reverse("logout"))
        # Debe ser 405 (Method Not Allowed) al estar restringido a POST
        self.assertEqual(resp.status_code, 405)

    def test_logout_post_cierra_sesion(self):
        self.client.login(username="user1", password="pass123")
        resp = self.client.post(reverse("logout"))
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)
        # Verificar que la sesión fue cerrada
        resp2 = self.client.get(reverse("dashboard"))
        self.assertEqual(resp2.status_code, 302)

    def test_login_superuser_redirige_admin(self):
        su = User.objects.create_superuser("admin", password="admin123")
        resp = self.client.post(reverse("login"), {"username": "admin", "password": "admin123"})
        self.assertRedirects(resp, reverse("admin:index"), fetch_redirect_response=False)


class RegistroViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_registro_get_renderiza_form(self):
        resp = self.client.get(reverse("registro"))
        self.assertEqual(resp.status_code, 200)

    def test_registro_post_crea_usuario(self):
        resp = self.client.post(reverse("registro"), {
            "username": "nuevo",
            "email": "nuevo@test.com",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        })
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="nuevo").exists())

    def test_registro_vincula_invitaciones_pendientes(self):
        """Al registrarse, si había invitación pendiente el user queda en ADMIN_EMPLEADO."""
        dueno = User.objects.create_user("dueno", password="pass")
        dueno.groups.add(make_group("ADMIN_DUENO"))
        cochera = Cochera.objects.create(owner=dueno, nombre="Cochera Test", activa=True)
        invitar_empleados(cochera, ["invitado@test.com"])

        self.client.post(reverse("registro"), {
            "username": "invitado",
            "email": "invitado@test.com",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        })

        user = User.objects.get(username="invitado")
        self.assertTrue(user.groups.filter(name="ADMIN_EMPLEADO").exists())
        self.assertTrue(CocheraEmpleado.objects.filter(cochera=cochera, empleado=user).exists())

    def test_registro_sin_invitacion_no_asigna_grupo(self):
        """Usuario que se registra sin invitación no tiene rol."""
        self.client.post(reverse("registro"), {
            "username": "libre",
            "email": "libre@test.com",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        })
        user = User.objects.get(username="libre")
        self.assertFalse(user.groups.filter(name__in=["ADMIN_DUENO", "ADMIN_EMPLEADO"]).exists())

    def test_registro_email_duplicado_falla(self):
        User.objects.create_user("primero", email="dup@test.com", password="pass")
        resp = self.client.post(reverse("registro"), {
            "username": "segundo",
            "email": "dup@test.com",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        })
        self.assertEqual(resp.status_code, 200)  # vuelve al form con error
        self.assertFalse(User.objects.filter(username="segundo").exists())


class DashboardViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.dueno = User.objects.create_user("dueno_dash", password="pass")
        self.dueno.groups.add(make_group("ADMIN_DUENO"))
        self.empleado = User.objects.create_user("emp_dash", password="pass")
        self.empleado.groups.add(make_group("ADMIN_EMPLEADO"))

    def test_dashboard_anon_redirige(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_dueno_ok(self):
        self.client.login(username="dueno_dash", password="pass")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["can_manage_cochera"])
        self.assertTrue(resp.context["can_operate"])

    def test_dashboard_empleado_no_puede_gestionar(self):
        self.client.login(username="emp_dash", password="pass")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_manage_cochera"])
        self.assertTrue(resp.context["can_operate"])

    def test_dashboard_usuario_sin_rol(self):
        sin_rol = User.objects.create_user("sin_rol", password="pass")
        self.client.login(username="sin_rol", password="pass")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["can_manage_cochera"])
        self.assertFalse(resp.context["can_operate"])
