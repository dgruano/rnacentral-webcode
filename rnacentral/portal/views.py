"""
Copyright [2009-2014] EMBL-European Bioinformatics Institute
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

from portal.models import Rna, Database, Release, Xref, Accession
from portal.forms import ContactForm

from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.shortcuts import render, render_to_response, redirect
from django.db.models import Min, Max, Count, Avg
from django.views.decorators.cache import cache_page, never_cache
from django.views.generic.base import TemplateView
from django.views.generic.edit import FormView
from django.template import TemplateDoesNotExist
import re
import requests
import json
from random import shuffle


CACHE_TIMEOUT = 60 * 60 * 24 * 1 # per-view cache timeout in seconds

########################
# Function-based views #
########################

def ebeye_proxy(request):
    """
    Internal API.
    Get EBeye search URL from the client and send back the results.
    Bypasses EBeye same-origin policy.
    """
    url = request.GET['url']
    try:
        response = requests.get(url)
        data = response.text
    except RequestException, exc:
        data = json.dumps({
            'status': 'failed',
        })
    return HttpResponse(data)


@cache_page(CACHE_TIMEOUT)
def get_expert_database_organism_sunburst(request, expert_db_name):
    """
    Internal API.
    Get lineages from all sequences for the sunburst diagram.
    """
    try:
        expert_db_name = _normalize_expert_db_name(expert_db_name)
        accessions = Accession.objects.only("classification").filter(database=expert_db_name).all()
        json_lineage_tree = _get_json_lineage_tree(accessions)
    except Exception, e:
        raise Http404
    return HttpResponse(json_lineage_tree, content_type="application/json")


@cache_page(CACHE_TIMEOUT)
def get_xrefs_data(request, upi):
    """
    Internal API.
    Get the data for the xrefs table. Improves DataTables performance for entries
    with thousands of cross-references.
    """
    try:
        rna = Rna.objects.get(upi=upi)
    except Rna.DoesNotExist:
        raise Http404
    return render(request, 'portal/xref-table.html', {'context': {'rna': rna}})


@cache_page(CACHE_TIMEOUT)
def get_sequence_lineage(request, upi):
    """
    Internal API.
    Get the lineage for an RNA sequence based on the
    classifications from all database cross-references.
    """
    try:
        xrefs = Xref.objects.filter(upi=upi).all()
        accessions = [xref.accession for xref in xrefs]
        json_lineage_tree = _get_json_lineage_tree(accessions)
    except Rna.DoesNotExist:
        raise Http404
    return HttpResponse(json_lineage_tree, content_type="application/json")


@cache_page(CACHE_TIMEOUT)
def homepage(request):
    """
    RNAcentral homepage.
    """
    context = dict()
    context['seq_count'] = Rna.objects.count()
    context['last_full_update'] = Release.objects.filter(release_type='F').order_by('-release_date').all()[0]
    try:
        context['last_daily_update'] = Release.objects.filter(release_type='I').order_by('-release_date').all()[0]
    except Exception, e:
        context['last_daily_update'] = context['last_full_update']
    context['databases'] = _get_database_data()
    shuffle(context['databases'])
    return render(request, 'portal/homepage.html', {'context': context})


@cache_page(CACHE_TIMEOUT)
def rna_view(request, upi):
    """
    Unique RNAcentral Sequence view.
    """
    try:
        rna = Rna.objects.get(upi=upi)
        context = {
            'counts': rna.count_symbols(),
        }
    except Rna.DoesNotExist:
        raise Http404
    return render(request, 'portal/unique-rna-sequence.html', {'rna': rna, 'context': context})


@cache_page(CACHE_TIMEOUT)
def expert_database_view(request, expert_db_name):
    """
    Expert database view.
    """
    context = dict()
    expert_db_name = _normalize_expert_db_name(expert_db_name)
    if expert_db_name and expert_db_name != 'coming_soon':
        data = Rna.objects.filter(xrefs__deleted='N', xrefs__db__descr=expert_db_name)
        context['expert_db'] = Database.objects.get(descr=expert_db_name)
        context['total_sequences'] = data.count()
        context['total_organisms'] = len(data.values('xrefs__taxid').annotate(n=Count("pk")))
        context['examples'] = data.all()[:8]
        for i, example in enumerate(context['examples']):
            context['examples'][i].upi = context['examples'][i].upi
        context['first_imported'] = data.order_by('xrefs__timestamp')[0].xrefs.all()[0].timestamp
        context['len_counts'] = data.values('length').annotate(counts=Count('length')).order_by('length')
        context.update(data.aggregate(min_length=Min('length'), max_length=Max('length'), avg_length=Avg('length')))
        return render_to_response('portal/expert-database.html', {'context': context})
    elif expert_db_name == 'coming_soon':
        return render_to_response('portal/expert-database-coming-soon.html', {'context': context})
    else:
        raise Http404()


@never_cache
def website_status_view(request):
    """
    This view will be monitored by Nagios for the presence
    of string "All systems operational".
    """
    def _is_database_up():
        try:
            rna = Rna.objects.all()[0]
            return True
        except:
            return False

    def _is_api_up():
        return True

    def _is_search_up():
        return True

    context = dict()
    context['is_database_up'] = _is_database_up()
    context['is_api_up'] = _is_api_up()
    context['is_search_up'] = _is_search_up()
    context['overall_status'] = context['is_database_up'] and context['is_api_up'] and context['is_search_up']
    return render_to_response('portal/website-status.html', {'context': context})

#####################
# Class-based views #
#####################

class StaticView(TemplateView):
    """
    Render flat pages.
    """
    def get(self, request, page, *args, **kwargs):
        self.template_name = 'portal/' + page + '.html'
        response = super(StaticView, self).get(request, *args, **kwargs)
        try:
            return response.render()
        except TemplateDoesNotExist:
            raise Http404()


class ContactView(FormView):
    """
    Contact form view.
    """
    template_name = 'portal/contact.html'
    form_class = ContactForm

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        if form.send_email():
            return redirect('contact-us-success')
        else:
            return redirect('error')

####################
# Helper functions #
####################

def _get_json_lineage_tree(accessions):
    """
    Combine lineages from multiple xrefs to produce a single species tree.
    The data are used by the d3 library.
    """

    def get_lineages(accessions):
        """
        Combine the lineages from all accessions in a single list.
        """
        taxons = []
        for accession in accessions:
            taxons.append(accession.classification)
        return taxons

    def build_nested_dict_helper(path, text, container):
        """
            Recursive function that builds the nested dictionary.
        """
        segs = path.split('; ')
        head = segs[0]
        tail = segs[1:]
        if not tail:
            # store how many time the species is seen
            try:
                if head in container:
                    container[head] += 1
                else:
                    container[head] = 1
            except:
                container = {}
                container[head] = 1
        else:
            if head not in container:
                container[head] = {}
            build_nested_dict_helper('; '.join(tail), text, container[head])

    def get_nested_dict(lineages):
        """
        Transform a list like this:
            items = [
                'A; C; X; human',
                'A; C; X; human',
                'B; D; Y; mouse',
                'B; D; Z; rat',
                'B; D; Z; rat',
            ]
        into a nested dictionary like this:
            {'root': {'A': {'C': {'X': {'human': 2}}}, 'B': {'D': {'Y': {'mouse': 1}, 'Z': {'rat': 2}}}}}
        """
        container = {}
        for lineage in lineages:
            build_nested_dict_helper(lineage, lineage, container)
        return container

    def get_nested_tree(data, container):
        """
        Transform a nested dictionary like this:
            {'root': {'A': {'C': {'X': {'human': 2}}}, 'B': {'D': {'Y': {'mouse': 1}, 'Z': {'rat': 2}}}}}
        into a json file like this (fragment shown):
            {"name":"A","children":[{"name":"C","children":[{"name":"X","children":[{"name":"human","size":2}]}]}]}
        """
        if not container:
            container = {
                "name": 'All',
                "children": []
            }
        for name, children in data.iteritems():
            if isinstance(children, int):
                container['children'].append({
                    "name": name,
                    "size": children
                })
            else:
                container['children'].append({
                    "name": name,
                    "children": []
                })
                get_nested_tree(children, container['children'][-1])
        return container

    lineages = get_lineages(accessions)
    nodes = get_nested_dict(lineages)
    json_lineage_tree = get_nested_tree(nodes, {})
    return json.dumps(json_lineage_tree)


def _normalize_expert_db_name(expert_db_name):
    """
    Expert_db_name should match RNACEN.RNC_DATABASE.DESCR
    """
    dbs = ('SRPDB', 'MIRBASE', 'VEGA', 'TMRNA_WEB')
    dbs_coming_soon = ('ENA', 'RFAM', 'LNCRNADB', 'GTRNADB')
    if re.match('tmrna-website', expert_db_name, flags=re.IGNORECASE):
        expert_db_name = 'TMRNA_WEB'
    else:
        expert_db_name = expert_db_name.upper()
    if expert_db_name in dbs:
        return expert_db_name
    elif expert_db_name in dbs_coming_soon:
        return 'coming_soon'
    else:
        return False

def _get_database_data():
    """
    The data about databases is stored in one place in order to reuse the same
    information on the homepage and on the expert database pages.
    Previously the data was retrieved from the database, but that was
    inconvenient for deployment and development purposes.
    """
    return [
        {
            'name': 'ENA',
            'label': 'ena',
            'url': 'http://www.ebi.ac.uk/ena/',
            'description': 'is an INSDC database that stores a wide range of sequence data',
            'abbreviation': 'European Nucleotide Archive',
            'examples': ['URS000000041', 'URS000000031'],
            'logo': 'ena.png',
            'seq_count': 6000000,
        },
        {
            'name': 'RFAM',
            'label': 'rfam',
            'url': 'http://rfam.xfam.org',
            'description': 'is a database containing information about ncRNA families and other structured RNA elements',
            'abbreviation': '',
            'examples': [],
            'logo': 'rfam.png',
            'seq_count': 0,
        },
        {
            'name': 'miRBase',
            'label': 'mirbase',
            'url': 'http://www.mirbase.org/',
            'description': 'is a database of published miRNA sequences and annotations',
            'abbreviation': '',
            'examples': ['URS0000026D73', 'URS0000026D73', 'URS00005BE7F9'],
            'logo': 'mirbase-logo-blue-web.png',
            'seq_count': 3661,
        },
        {
            'name': 'VEGA',
            'label': 'vega',
            'url': 'http://vega.sanger.ac.uk/',
            'description': 'is a repository for high-quality gene models produced by the manual annotation of vertebrate genomes',
            'abbreviation': 'Vertebrate Genome Annotation',
            'examples': ['URS000063A371', 'URS000063A296', 'URS0000638AD4'],
            'logo': 'vega.gif',
            'seq_count': 21388,
        },
        {
            'name': 'tmRNA Website',
            'label': 'tmrna-website',
            'url': 'http://bioinformatics.sandia.gov/tmrna/',
            'description': 'contains predicted tmRNA sequences from RefSeq prokaryotic genomes, plasmids and bacteriophages',
            'abbreviation': '',
            'examples': ['URS0000646B13', 'URS000064AECD', 'URS000064B0CC'],
            'logo': 'tmlogo.png',
            'seq_count': 21318,
        },
        {
            'name': 'SRPDB',
            'label': 'srpdb',
            'url': 'http://rnp.uthscsa.edu/rnp/SRPDB/SRPDB.html',
            'description': 'provides aligned, annotated and phylogenetically ordered sequences related to structure and function of SRP',
            'abbreviation': 'Signal Recognition Particle Database',
            'examples': ['URS000030A37C', 'URS0000227674', 'URS000005F2FD'],
            'logo': 'SRPLogo-small.gif',
            'seq_count': 855,
        },
        {
            'name': 'lncRNAdb',
            'label': 'lncrnadb',
            'url': 'http://lncrnadb.org/',
            'description': 'is a database providing comprehensive annotations of eukaryotic long non-coding RNAs (lncRNAs)',
            'abbreviation': '',
            'examples': [],
            'logo': 'lncrnadb.png',
            'seq_count': 0,
        },
        {
            'name': 'gtRNAdb',
            'url': 'http://gtrnadb.ucsc.edu/',
            'description': 'contains tRNA gene predictions on complete or nearly complete genomes',
            'abbreviation': '',
            'examples': [],
            'logo': 'gtrnadb.png',
            'seq_count': 0,
        },
    ]
