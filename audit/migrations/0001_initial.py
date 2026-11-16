from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Event",fields=[
            ("id",models.BigAutoField(primary_key=True,serialize=False)),
            ("area",models.CharField(max_length=40)),
            ("action",models.CharField(max_length=255)),
            ("reference",models.CharField(max_length=100)),
            ("details",models.JSONField(default=dict,blank=True)),
            ("created",models.DateTimeField(auto_now_add=True,db_index=True)),
            ("actor",models.ForeignKey(to=settings.AUTH_USER_MODEL,null=True,on_delete=django.db.models.deletion.SET_NULL)),
        ],options={"ordering":("-created",)}),
    ]
