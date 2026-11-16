from django.contrib.auth.models import Group, Permission

ROLES = {
    "bibliotecario": ("catalog.manage_collection", "accounts.manage_credential", "audit.view_event"),
    "tecnico": (),
    "correccao": ("accounts.correct_number",),
}


def ensure_role(name):
    group, _ = Group.objects.get_or_create(name=name)
    permissions = []
    for code in ROLES[name]:
        app, codename = code.split(".")
        permissions.append(Permission.objects.get(content_type__app_label=app, codename=codename))
    group.permissions.set(permissions)
    return group
