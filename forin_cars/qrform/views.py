import io
import qrcode

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import SubmissionForm
from .models import QRLink


def qr_new(request):
    """
    Página con botón: genera un QRLink y redirige a su detalle.
    """
    if request.method == "POST":
        # Podés setear expiración si querés (ej: 24hs)
        expires_at = timezone.now() + timezone.timedelta(hours=24)

        qr = QRLink.objects.create(
            expires_at=expires_at,
            max_uses=1,
            is_active=True,
        )
        return redirect("qrforms:qr_detail", token=qr.token)

    return render(request, "qrforms/qr_new.html")


def qr_detail(request, token):
    qr = get_object_or_404(QRLink, token=token)

    scan_url = request.build_absolute_uri(reverse("qrforms:qr_form", kwargs={"token": qr.token}))
    img_url = reverse("qrforms:qr_image", kwargs={"token": qr.token})

    return render(
        request,
        "qrforms/qr_detail.html",
        {"qr": qr, "scan_url": scan_url, "img_url": img_url},
    )


def qr_image(request, token):
    """
    Devuelve el PNG del QR.
    """
    qr = get_object_or_404(QRLink, token=token)

    scan_path = reverse("qrforms:qr_form", kwargs={"token": qr.token})
    scan_url = request.build_absolute_uri(scan_path)

    img = qrcode.make(scan_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return HttpResponse(buf.getvalue(), content_type="image/png")


def qr_form(request, token):
    """
    Form accesible al escanear el QR.
    """
    qr = get_object_or_404(QRLink, token=token)

    if not qr.can_be_used():
        raise Http404("QR inválido, vencido o sin usos disponibles.")

    if request.method == "POST":
        form = SubmissionForm(request.POST)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.qr_link = qr
            submission.save()

            # Consume el uso (control anti-reuso)
            qr.uses_count += 1
            if qr.uses_count >= qr.max_uses:
                qr.is_active = False
            qr.save(update_fields=["uses_count", "is_active"])

            return redirect("qrforms:qr_success", token=qr.token)
    else:
        form = SubmissionForm()

    return render(request, "qrforms/qr_form.html", {"qr": qr, "form": form})


def qr_success(request, token):
    qr = get_object_or_404(QRLink, token=token)
    return render(request, "qrforms/qr_success.html", {"qr": qr})
