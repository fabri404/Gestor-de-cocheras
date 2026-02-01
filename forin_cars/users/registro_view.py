from django.contrib.auth.models import Group
from models import user

g_dueno = Group.objects.get(name="ADMIN_DUENO")
user.groups.add(g_dueno)

# importante: que NO sea staff, para que no vea admin
user.is_staff = False
user.save()
