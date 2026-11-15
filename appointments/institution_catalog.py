"""IPS de Cartagena verificadas en sus canales institucionales, 14/11/2026.
El catálogo no acredita convenios con EPS ni disponibilidad de servicios o agendas.
"""
REAL_INSTITUTIONS = (
    ('E.S.E. Hospital Universitario del Caribe', 'Zaragocilla, Calle 29 # 50-50', 'https://www.hucaribe.gov.co/contactenos/'),
    ('Clínica Medihelp Services', 'Bocagrande, Carrera 6A # 5-101', 'https://www.clinicamedihelp.com/contactenos/'),
    ('Clínica Blas de Lezo', 'Transversal 54 # 47-57, Avenida El Bosque', 'https://clinicablasdelezo.com.co/contact/'),
    ('E.S.E. Clínica de Maternidad Rafael Calvo C.', 'Alcibia, sector María Auxiliadora', 'https://maternidadrafaelcalvo.gov.co/'),
    ('Hospital Infantil Napoleón Franco Pareja', 'Bruselas, Transversal 36 # 36-33', 'https://lacasadelnino.org/'),
)

def selectable_institutions():
    from .models import Institution
    return Institution.objects.filter(is_active=True, name__in=[row[0] for row in REAL_INSTITUTIONS]).order_by('name')
