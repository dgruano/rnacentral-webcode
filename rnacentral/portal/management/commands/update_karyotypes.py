"""
Copyright [2009-2017] EMBL-European Bioinformatics Institute
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
     http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from __future__ import print_function

import requests

from django.core.management.base import BaseCommand

from portal.models import EnsemblAssembly, EnsemblKaryotype


class Command(BaseCommand):
    """
    Usage:
    python manage.py update_karyotypes
    """
    def add_arguments(self, parser):
        parser.add_argument(
            '--ensembl_url',
            type=str,
            help='specific assembly, e.g. homo_sapiens'
        )

    def fetch_ensembl_karyotype(self, ensembl_url, domain):
        response = requests.get(
            'http://rest.%s.org/info/assembly/%s?bands=1' % (domain, ensembl_url),
            headers={'Content-Type': 'application/json'}
        )

        response.raise_for_status()

        result = {}
        for data in response.json()["top_level_region"]:
            if data["coord_system"] == "chromosome":
                try:
                    bands = []
                    for band in data["bands"]:
                        bands.append({
                            "id": band["id"],
                            "start": band["start"],
                            "end": band["end"],
                            "type": band["stain"]
                        })

                    result[data["name"]] = {
                        "size": data["length"],
                        "bands": bands
                    }
                except KeyError:  # bands not defined
                    start = 1
                    end = data["length"]

                    result[data["name"]] = {
                        "size": data["length"],
                        "bands": [{
                            "start": start,
                            "end": end
                        }]
                    }

            elif data["coord_system"] == "scaffold":
                result[data["name"]] = {
                    "size": data["length"],
                    "bands": [{
                        "start": 1,
                        "end": data["length"]
                    }]
                }

        return result

    def store_ensembl_karyotype(self, karyotype):
        EnsemblKaryotype.objects.create(
            karyotype=karyotype,
            assembly_id=EnsemblAssembly.objects.get()
        )

    def process_ensembl_karyotype(self, assembly):
        print("Retrieving kartyotype for: %s" % assembly.ensembl_url)

        EnsemblKaryotype.objects.filter(assembly_id=assembly.assembly_id).delete()

        if assembly.division == 'Ensembl':
            domain = 'ensembl'
        else:
            domain = 'ensemblgenomes'

        karyotype = self.fetch_ensembl_karyotype(ensembl_url=assembly.ensembl_url, domain=domain)
        EnsemblKaryotype.objects.create(assembly_id=assembly, karyotype=karyotype)

    def handle(self, *args, **options):
        """Main function, called by django."""
        if 'ensembl_url' in options:
            assembly = EnsemblAssembly.objects.filter(ensembl_url=options['ensembl_url']).first()
            self.process_ensembl_karyotype(assembly)
        else:
            for assembly in EnsemblAssembly.objects.all():
                self.process_ensembl_karyotype(assembly)
