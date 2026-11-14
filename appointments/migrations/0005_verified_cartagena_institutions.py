from django.db import migrations

INSTITUTIONS = (('E.S.E. Hospital Universitario del Caribe', 'Zaragocilla, Calle 29 # 50-50', 'https://www.hucaribe.gov.co/contactenos/'), ('Clínica Medihelp Services', 'Bocagrande, Carrera 6A # 5-101', 'https://www.clinicamedihelp.com/contactenos/'), ('Clínica Blas de Lezo', 'Transversal 54 # 47-57, Avenida El Bosque', 'https://clinicablasdelezo.com.co/contact/'), ('E.S.E. Clínica de Maternidad Rafael Calvo C.', 'Alcibia, sector María Auxiliadora', 'https://maternidadrafaelcalvo.gov.co/'), ('Hospital Infantil Napoleón Franco Pareja', 'Bruselas, Transversal 36 # 36-33', 'https://lacasadelnino.org/'))

def load_verified_institutions(apps, schema_editor):
    Institution = apps.get_model('appointments', 'Institution')
    for name, address, source in INSTITUTIONS:
        Institution.objects.using(schema_editor.connection.alias).get_or_create(
            name=name, defaults={'city':'Cartagena', 'address':address, 'is_active':True})

class Migration(migrations.Migration):
    dependencies = [('appointments','0004_requestpatientdetails')]
    operations = [migrations.RunPython(load_verified_institutions, migrations.RunPython.noop)]
