import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo13-addons-oca-l10n-brazil",
    description="Meta package for oca-l10n-brazil Odoo addons",
    version=version,
    install_requires=[
        'odoo13-addon-l10n_br_base',
        'odoo13-addon-l10n_br_coa',
        'odoo13-addon-l10n_br_coa_generic',
        'odoo13-addon-l10n_br_coa_simple',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
    ]
)
