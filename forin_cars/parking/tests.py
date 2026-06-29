"""
Tests de regresión — app parking.

Cobertura:
- Permisos por rol (is_admin_dueno, can_operate, cochera_queryset_for)
- Flujo ingreso → egreso (Movimiento, Espacio, cálculo Decimal, mínimo 1h)
- Inventario: AJUSTE absoluto, SALIDA valida stock
- Onboarding: apply_pending_invites vincula empleado a cochera
- Smoke tests de vistas clave (no 500 por NameError/NoReverseMatch)
"""
from decimal import Decimal

from django.contrib.auth.models import User, Group
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from .models import (
    Cochera,
    CocheraEmpleado,
    InvitacionEmpleado,
    TipoEspacio,
    ConfigCapacidad,
    TarifaHora,
    Espacio,
    Movimiento,
    Cliente as ClienteModel,
    Vehiculo,
    CategoriaProducto,
    Producto,
    MovimientoInventario,
    Servicio,
    OrdenTrabajo,
    ChecklistItem,
    Plan,
    Membresia,
)
from .services import apply_pending_invites, invitar_empleados, regenerar_espacios
from .services_movimientos import ingresar_vehiculo, egresar_vehiculo


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_group(name: str) -> Group:
    g, _ = Group.objects.get_or_create(name=name)
    return g


def make_dueno(username="dueno") -> User:
    user = User.objects.create_user(username=username, password="pass", email=f"{username}@test.com")
    user.groups.add(make_group("ADMIN_DUENO"))
    return user


def make_empleado(username="empleado") -> User:
    user = User.objects.create_user(username=username, password="pass", email=f"{username}@test.com")
    user.groups.add(make_group("ADMIN_EMPLEADO"))
    return user


def make_cochera(owner, nombre="Test Cochera") -> Cochera:
    return Cochera.objects.create(owner=owner, nombre=nombre, activa=True)


def make_tipo(nombre="Auto") -> TipoEspacio:
    t, _ = TipoEspacio.objects.get_or_create(nombre=nombre)
    return t


def setup_cochera_operativa(owner, tipo_nombre="Auto", capacidad=5, precio_hora=100):
    """Crea cochera + tipo + capacidad + tarifa + espacios."""
    cochera = make_cochera(owner)
    tipo = make_tipo(tipo_nombre)
    ConfigCapacidad.objects.create(cochera=cochera, tipo=tipo, cantidad=capacidad)
    TarifaHora.objects.create(cochera=cochera, tipo=tipo, precio_hora=Decimal(str(precio_hora)))
    regenerar_espacios(cochera)
    return cochera, tipo


# ─── Tests de permisos ────────────────────────────────────────────────────────

class PermisosRolTests(TestCase):
    def setUp(self):
        self.dueno = make_dueno()
        self.empleado = make_empleado()
        self.otro = User.objects.create_user("otro", password="pass")
        self.superuser = User.objects.create_superuser("super", password="pass")

    def test_is_admin_dueno_con_grupo(self):
        from .views import is_admin_dueno
        self.assertTrue(is_admin_dueno(self.dueno))
        self.assertFalse(is_admin_dueno(self.empleado))
        self.assertFalse(is_admin_dueno(self.otro))
        self.assertTrue(is_admin_dueno(self.superuser))

    def test_can_operate_incluye_dueno_y_empleado(self):
        from .views import can_operate
        self.assertTrue(can_operate(self.dueno))
        self.assertTrue(can_operate(self.empleado))
        self.assertFalse(can_operate(self.otro))
        self.assertTrue(can_operate(self.superuser))

    def test_cochera_queryset_for_dueno_solo_ve_las_suyas(self):
        from .views import cochera_queryset_for
        cochera_propia = make_cochera(self.dueno, "Mia")
        make_cochera(make_dueno("otro_dueno"), "Ajena")
        qs = cochera_queryset_for(self.dueno)
        self.assertIn(cochera_propia, qs)
        self.assertEqual(qs.count(), 1)

    def test_cochera_queryset_for_empleado_ve_asignadas(self):
        from .views import cochera_queryset_for
        cochera, _ = setup_cochera_operativa(self.dueno)
        CocheraEmpleado.objects.create(cochera=cochera, empleado=self.empleado, activo=True)
        qs = cochera_queryset_for(self.empleado)
        self.assertIn(cochera, qs)

    def test_cochera_queryset_for_superuser_ve_todo(self):
        from .views import cochera_queryset_for
        make_cochera(self.dueno, "C1")
        make_cochera(make_dueno("d2"), "C2")
        qs = cochera_queryset_for(self.superuser)
        self.assertEqual(qs.count(), 2)


# ─── Tests de flujo ingreso/egreso ───────────────────────────────────────────

class IngresoEgresoTests(TestCase):
    def setUp(self):
        self.dueno = make_dueno()
        self.cochera, self.tipo = setup_cochera_operativa(self.dueno, precio_hora=200)

    def test_ingreso_crea_movimiento_y_ocupa_espacio(self):
        mov = ingresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            tipo=self.tipo,
            patente_ult3="ABC",
        )
        self.assertEqual(mov.estado, Movimiento.ABIERTO)
        espacio = Espacio.objects.get(id=mov.espacio_id)
        self.assertTrue(espacio.ocupado)

    def test_ingreso_sin_tarifa_lanza_error(self):
        tipo_sin_tarifa = TipoEspacio.objects.create(nombre="Moto")
        Espacio.objects.create(cochera=self.cochera, tipo=tipo_sin_tarifa, ocupado=False)
        with self.assertRaises(ValueError):
            ingresar_vehiculo(
                cochera=self.cochera,
                operador=self.dueno,
                tipo=tipo_sin_tarifa,
            )

    def test_ingreso_doble_lanza_error(self):
        ingresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            tipo=self.tipo,
            ticket="TKT-ABCDEF01",
            patente_ult3="XYZ",
        )
        with self.assertRaises(ValueError):
            ingresar_vehiculo(
                cochera=self.cochera,
                operador=self.dueno,
                tipo=self.tipo,
                ticket="TKT-ABCDEF01",
                patente_ult3="XYZ",
            )

    def test_egreso_cierra_movimiento_y_libera_espacio(self):
        mov = ingresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            tipo=self.tipo,
            ticket="TKT-TEST0001",
            patente_ult3="LMN",
        )
        mov_cerrado = egresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            ticket="TKT-TEST0001",
        )
        self.assertEqual(mov_cerrado.estado, Movimiento.CERRADO)
        espacio = Espacio.objects.get(id=mov_cerrado.espacio_id)
        self.assertFalse(espacio.ocupado)

    def test_monto_acumulado_usa_decimal_y_minimo_una_hora(self):
        mov = ingresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            tipo=self.tipo,
            patente_ult3="DEC",
        )
        # Forzar ingreso hace ~5 minutos → sin mínimo sería ~$16.67; con mínimo debe ser $200
        mov.ingreso_at = timezone.now() - timezone.timedelta(minutes=5)
        mov.save(update_fields=["ingreso_at"])
        monto = mov.monto_acumulado()
        self.assertIsInstance(monto, Decimal)
        self.assertEqual(monto, Decimal("200.00"))  # mínimo 1 hora × $200/h

    def test_monto_acumulado_horas_completas(self):
        mov = ingresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            tipo=self.tipo,
            patente_ult3="HRS",
        )
        # 3 horas exactas
        mov.ingreso_at = timezone.now() - timezone.timedelta(hours=3)
        mov.save(update_fields=["ingreso_at"])
        monto = mov.monto_acumulado()
        self.assertEqual(monto, Decimal("600.00"))  # 3h × $200/h

    def test_monto_acumulado_membresia_es_cero(self):
        mov = ingresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            tipo=self.tipo,
            patente_ult3="MEM",
        )
        mov.tipo_pago = Movimiento.MEMBRESIA
        mov.save(update_fields=["tipo_pago"])
        monto = mov.monto_acumulado()
        self.assertEqual(monto, Decimal("0.00"))

    def test_egreso_ticket_inexistente_lanza_error(self):
        with self.assertRaises(ValueError):
            egresar_vehiculo(
                cochera=self.cochera,
                operador=self.dueno,
                ticket="TKT-NOEXISTE",
            )


# ─── Tests de inventario ─────────────────────────────────────────────────────

class InventarioTests(TestCase):
    def setUp(self):
        self.dueno = make_dueno()
        self.cochera = make_cochera(self.dueno)
        cat = CategoriaProducto.objects.create(nombre="Limpieza")
        self.producto = Producto.objects.create(
            cochera=self.cochera,
            nombre="Shampoo",
            categoria=cat,
            stock_actual=Decimal("10.00"),
            stock_minimo=Decimal("2.00"),
        )

    def test_entrada_suma_stock(self):
        MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.ENTRADA,
            cantidad=Decimal("5.00"),
            operador=self.dueno,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("15.00"))

    def test_salida_resta_stock(self):
        MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.SALIDA,
            cantidad=Decimal("3.00"),
            operador=self.dueno,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("7.00"))

    def test_ajuste_fija_stock_absoluto(self):
        """AJUSTE debe fijar el stock al valor indicado, no sumar."""
        MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.AJUSTE,
            cantidad=Decimal("8.00"),  # stock real contado = 8 (no 18)
            operador=self.dueno,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("8.00"))

    def test_ajuste_puede_reducir_stock(self):
        """Ajuste a valor menor que el actual debe funcionar."""
        MovimientoInventario.objects.create(
            producto=self.producto,
            tipo=MovimientoInventario.AJUSTE,
            cantidad=Decimal("2.00"),
            operador=self.dueno,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("2.00"))

    def test_bajo_stock_property(self):
        self.producto.stock_actual = Decimal("2.00")
        self.producto.save()
        self.assertTrue(self.producto.bajo_stock)
        self.producto.stock_actual = Decimal("3.00")
        self.producto.save()
        self.assertFalse(self.producto.bajo_stock)


# ─── Tests de onboarding / invitación ────────────────────────────────────────

class OnboardingInvitacionTests(TestCase):
    def setUp(self):
        self.dueno = make_dueno()
        self.cochera, _ = setup_cochera_operativa(self.dueno)

    def test_apply_pending_invites_vincula_empleado(self):
        """Empleado que se registra con email invitado queda en cochera y en ADMIN_EMPLEADO."""
        # Dueño invita
        invitar_empleados(self.cochera, ["nuevo@test.com"])
        inv = InvitacionEmpleado.objects.get(cochera=self.cochera, email="nuevo@test.com")
        self.assertEqual(inv.estado, InvitacionEmpleado.PENDIENTE)

        # Empleado se registra
        nuevo = User.objects.create_user("nuevo", password="pass", email="nuevo@test.com")
        aceptadas = apply_pending_invites(nuevo)

        self.assertEqual(aceptadas, 1)
        self.assertTrue(nuevo.groups.filter(name="ADMIN_EMPLEADO").exists())
        self.assertTrue(CocheraEmpleado.objects.filter(cochera=self.cochera, empleado=nuevo).exists())
        inv.refresh_from_db()
        self.assertEqual(inv.estado, InvitacionEmpleado.ACEPTADA)

    def test_apply_pending_invites_sin_invitacion_retorna_0(self):
        user = User.objects.create_user("sinInv", password="pass", email="sin@test.com")
        aceptadas = apply_pending_invites(user)
        self.assertEqual(aceptadas, 0)
        self.assertFalse(user.groups.filter(name="ADMIN_EMPLEADO").exists())

    def test_invitar_empleado_existente_lo_vincula_inmediatamente(self):
        """Si el user ya existe al momento de invitar, queda vinculado."""
        existente = User.objects.create_user(
            "existente", password="pass", email="existente@test.com"
        )
        invitar_empleados(self.cochera, ["existente@test.com"])
        existente.refresh_from_db()
        self.assertTrue(existente.groups.filter(name="ADMIN_EMPLEADO").exists())


# ─── Smoke tests de vistas (no 500 por NameError/NoReverseMatch) ─────────────

class SmokeParkingViewsTests(TestCase):
    """
    Cada vista clave debe responder 200 o redirect (302/301).
    Un 500 indica NameError, NoReverseMatch o TemplateDoesNotExist.
    """

    def setUp(self):
        self.client = Client()
        self.dueno = make_dueno("dueno_smoke")
        self.cochera, self.tipo = setup_cochera_operativa(self.dueno)

    def _login_dueno(self):
        self.client.login(username="dueno_smoke", password="pass")

    def test_dashboard_redirige_anon(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_ok_dueno(self):
        self._login_dueno()
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_cochera_live_ok(self):
        self._login_dueno()
        url = reverse("parking:cochera_live", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_ingreso_view_get_ok(self):
        self._login_dueno()
        url = reverse("parking:ingreso_cochera", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_egreso_view_get_ok(self):
        self._login_dueno()
        url = reverse("parking:egreso_cochera", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_servicios_list_ok(self):
        self._login_dueno()
        url = reverse("parking:servicios_list", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_clientes_list_ok(self):
        self._login_dueno()
        url = reverse("parking:clientes_list", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_ordenes_list_ok(self):
        self._login_dueno()
        url = reverse("parking:ordenes_list", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_inventario_list_ok(self):
        self._login_dueno()
        url = reverse("parking:inventario_list", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_planes_list_ok(self):
        self._login_dueno()
        url = reverse("parking:planes_list", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_cochera_new_get_ok(self):
        self._login_dueno()
        url = reverse("parking:cochera_new")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_cochera_qr_ok(self):
        self._login_dueno()
        url = reverse("parking:cochera_qr", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_turnos_list_ok(self):
        self._login_dueno()
        url = reverse("parking:turnos_list", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_empleado_no_puede_acceder_a_cochera_new(self):
        emp = make_empleado("emp_smoke")
        self.client.login(username="emp_smoke", password="pass")
        url = reverse("parking:cochera_new")
        resp = self.client.get(url)
        # user_passes_test falla → redirect a login
        self.assertEqual(resp.status_code, 302)

    def test_anon_cochera_live_redirige_login(self):
        url = reverse("parking:cochera_live", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])

    def test_ingreso_post_genera_pdf_ticket(self):
        """POST en ingreso genera PDF (content-type application/pdf)."""
        self._login_dueno()
        url = reverse("parking:ingreso_cochera", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.post(url, {
            "tipo_id": self.tipo.id,
            "ticket": "",
            "patente_ult3": "TST",
            "tipo_pago": Movimiento.HORA,
            "horas": 2,
            "nombre": "Juan",
            "apellido": "Test",
            "telefono": "",
            "email": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_egreso_post_valido_redirige_a_live(self):
        """POST en egreso con ticket válido → redirect a cochera_live."""
        self._login_dueno()
        # Ingresar primero
        mov = ingresar_vehiculo(
            cochera=self.cochera,
            operador=self.dueno,
            tipo=self.tipo,
            ticket="TKT-SMOKE001",
            patente_ult3="EGR",
        )
        url = reverse("parking:egreso_cochera", kwargs={"cochera_id": self.cochera.id})
        resp = self.client.post(url, {"ticket": "TKT-SMOKE001"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("live", resp["Location"])
