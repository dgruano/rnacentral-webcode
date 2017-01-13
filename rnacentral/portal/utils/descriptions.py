"""A module to help with selecting the descriptions of various RNA molecules.
"""

CHOICES = {
    'miRNA': ['MIRBASE', 'RefSeq', 'Rfam', 'HGNC', 'ENA'],
    'precusor_RNA': ['RefSeq', 'MIRBASE', 'Rfam', 'HGNC', 'ENA'],
}


def can_apply_new_method(sequence):
    return sequence.rna_type in CHOICES


def best_from(ordered_choices, possible, check, default=None):
    for choice in ordered_choices:
        if check(choice, possible):
            return possible[choice]
    return default


def generic_name(rna_type, sequence):
    species_count = len({xref.taxid for xref in sequence.xrefs})
    return '%s found in %i species' % (rna_type, species_count)


def default_species_name(sequence):
    rna_type = '/'.join(sequence.rna_type)
    return '%s found in %s' % (rna_type, sequence.species_name)


def species_name(sequence, taxid):
    def is_good_xref(name, xref):
        return xref.database == name

    def xref_agrees(xref):
        return xref.rna_type == sequence.rna_type

    return best_from(CHOICES,
                     sequence.xrefs,
                     is_good_xref,
                     xref_agrees,
                     default=default_species_name(sequence))


def determine_rna_type_for(sequence):
    pass


def description_of(sequence, taxid=None):
    if not can_apply_new_method(sequence, taxid):
        return previous_method(sequence, taxid=taxid)

    rna_type = determine_rna_type_for(sequence)
    if taxid is None:
        return generic_name(rna_type, sequence)
    return species_name(rna_type, sequence, taxid)


def previous_method(sequence, taxid=None, recompute=False):
    """
    Get entry description based on its xrefs.
    If taxid is provided, use only species-specific xrefs.
    """
    def count_distinct_descriptions():
        """
        Count distinct description lines.
        """
        queryset = xrefs.values_list('accession__description', flat=True)
        results = queryset.filter(deleted='N').distinct().count()
        if not results:
            results = queryset.distinct().count()
        return results

    def get_distinct_products():
        """
        Get distinct non-null product values as a list.
        """
        queryset = xrefs.values_list('accession__product', flat=True).\
            filter(accession__product__isnull=False)
        results = queryset.filter(deleted='N').distinct()
        if not results:
            results = queryset.distinct()
        return results

    def get_distinct_genes():
        """
        Get distinct non-null gene values as a list.
        """
        queryset = xrefs.values_list('accession__gene', flat=True).\
            filter(accession__gene__isnull=False)
        results = queryset.filter(deleted='N').distinct()
        if not results:
            results = queryset.distinct()
        return results

    def get_distinct_feature_names():
        """
        Get distinct feature names as a list.
        """
        queryset = xrefs.values_list('accession__feature_name', flat=True)
        results = queryset.filter(deleted='N').distinct()
        if not results:
            results = queryset.distinct()
        return results

    def get_distinct_ncrna_classes():
        """
        For ncRNA features, get distinct ncrna_class values as a list.
        """
        queryset = xrefs.values_list('accession__ncrna_class', flat=True).\
            filter(accession__ncrna_class__isnull=False)
        results = queryset.filter(deleted='N').distinct()
        if not results:
            results = queryset.distinct()
        return results

    def get_rna_type():
        """
        product > gene > feature name
        For ncRNA features, use ncrna_class annotations.
        """
        products = get_distinct_products()
        genes = get_distinct_genes()
        if len(products) == 1:
            rna_type = products[0]
        elif len(genes) == 1:
            rna_type = genes[0]
        else:
            feature_names = get_distinct_feature_names()
            if feature_names[0] == 'ncRNA' and len(feature_names) == 1:
                ncrna_classes = get_distinct_ncrna_classes()
                if len(ncrna_classes) > 1 and 'misc_RNA' in ncrna_classes:
                    ncrna_classes.remove('misc_RNA')
                rna_type = '/'.join(ncrna_classes)
            else:
                rna_type = '/'.join(feature_names)
        return rna_type

    def get_urs_description():
        """
        Get a description for a URS identifier, including multiple species.
        """
        if count_distinct_descriptions() == 1:
            description_line = xrefs.first().accession.description
            description_line = description_line[0].upper() + description_line[1:]
        else:
            rna_type = get_rna_type()
            distinct_species = sequence.count_distinct_organisms
            if taxid or distinct_species == 1:
                species = xrefs.first().accession.species
                description_line = '{species} {rna_type}'.format(
                                    species=species, rna_type=rna_type)
            else:
                description_line = ('{rna_type} from '
                                    '{distinct_species} species').format(
                                    rna_type=rna_type,
                                    distinct_species=distinct_species)
        return description_line

    def get_xrefs_for_description(taxid):
        """
        Get cross-references for building a description line.
        """
        # try only active xrefs first
        if taxid:
            xrefs = sequence.xrefs.filter(deleted='N', taxid=taxid)
        else:
            xrefs = sequence.xrefs.filter(deleted='N')
        # fall back onto all xrefs if no active ones are found
        if not xrefs.exists():
            if taxid:
                xrefs = sequence.xrefs.filter(taxid=taxid)
            else:
                xrefs = sequence.xrefs.filter()
        return xrefs.select_related('accession').\
            prefetch_related('accession__refs', 'accession__coordinates')

    def score_xref(xref):
        """
        Return a score for a cross-reference based on its metadata.
        """
        def get_genome_bonus():
            """
            Find if the xref has genome mapping.
            Iterate over prefetched queryset to avoid hitting the database.
            """
            chromosomes = []
            for coordinate in xref.accession.coordinates.all():
                chromosomes.append(coordinate.chromosome)
            if not chromosomes:
                return 0
            else:
                return 1

        paper_bonus = xref.accession.refs.count() * 0.2
        genome_bonus = get_genome_bonus()
        gene_bonus = 0
        note_bonus = 0
        product_bonus = 0
        rfam_full_alignment_penalty = 0
        misc_rna_penalty = 0

        if xref.accession.product:
            product_bonus = 0.1
        if xref.accession.gene:
            gene_bonus = 0.1
        if xref.db_id == 2 and not xref.is_rfam_seed():
            rfam_full_alignment_penalty = -2
        if xref.accession.feature_name == 'misc_RNA':
            misc_rna_penalty = -2
        if xref.accession.note:
            note_bonus = 0.1

        score = paper_bonus + \
            genome_bonus + \
            gene_bonus + \
            product_bonus + \
            note_bonus + \
            rfam_full_alignment_penalty + \
            misc_rna_penalty
        return score

    # blacklisted entries, an entry with > 200K xrefs, all from Rfam
    if sequence.upi in ['URS000065859A'] and not taxid:
        return 'uncultured Neocallimastigales 5.8S ribosomal RNA'

    # get description
    if taxid and not sequence.xref_with_taxid_exists(taxid):
        taxid = None  # ignore taxid

    xrefs = get_xrefs_for_description(taxid)
    if not taxid:
        return get_urs_description()
    else:
        # pick one of expert database descriptions
        scores = []
        for xref in xrefs:
            scores.append((score_xref(xref), xref.accession.description))
        scores.sort(key=lambda tup: tup[0], reverse=True)
        return scores[0][1]
