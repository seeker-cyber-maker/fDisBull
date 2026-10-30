"""Projectless JSON methods for the private, collection-wide source catalog."""

METHODS = {
    'source-create': 'Create a private source catalog; catalog',
    'source-info': 'Source catalog counts and scope; catalog',
    'source-import': 'Snapshot explicit source paths; catalog,root,paths,repository,revision,edition,source_role,[target_path,declared_output_sha256,parse_c]',
    'source-snapshots': 'List pinned source editions and native-target associations; catalog,[offset,limit]',
    'source-files': 'List retained source files and parser coverage; catalog,[snapshot,offset,limit]',
    'source-entities': 'List syntax candidates; catalog,[snapshot,name,kind,offset,limit]',
    'source-text': 'Read bounded immutable source text; catalog,entity,[offset,size]',
    'source-occurrences': 'Exact spelling occurrences, without binding resolution; catalog,name,[snapshot,offset,limit]',
    'source-cards': 'Export bounded retrieval cards, optionally only missing vectors; catalog,[model,offset,limit]',
    'source-model': 'Register an immutable embedding model/preprocessing identity; catalog,name,revision,dimensions,preprocessing',
    'source-models': 'Discover saved embedding model identities/profiles; catalog,[offset,limit]',
    'source-embed': 'Import explicit card embeddings; catalog,model,items',
    'source-search': 'Rank source candidates; catalog,query,[mode,model,vector,snapshots,kind,limit]',
    'source-concept': 'Register an immutable logical concept; catalog,key,description,[unit,author]',
    'source-concepts': 'Discover saved concepts by optional logical key; catalog,[key,offset,limit]',
    'source-link': 'Record an authored concept/entity relationship; catalog,concept,entity,relation,evidence,[assurance,author]',
    'source-bindings': 'Enumerate recorded concept relationships exactly; catalog,concept,[offset,limit]',
}

OPERATIONS = {
    'source-info': 'info', 'source-import': 'import_tree', 'source-snapshots': 'snapshots', 'source-files': 'files',
    'source-entities': 'entities', 'source-text': 'source_text', 'source-occurrences': 'occurrences',
    'source-cards': 'cards', 'source-model': 'register_model', 'source-models': 'models', 'source-embed': 'embed_cards',
    'source-search': 'search', 'source-concept': 'register_concept', 'source-link': 'link_concept',
    'source-bindings': 'concept_bindings', 'source-concepts': 'concepts',
}


def invoke(method, params):
    from .source_catalog import SourceCatalog
    params = dict(params)
    path = params.pop('catalog')
    if method == 'source-create':
        if params:
            raise ValueError('source-create accepts only catalog')
        with SourceCatalog.create(path) as catalog:
            return catalog.info()
    with SourceCatalog(path) as catalog:
        return getattr(catalog, OPERATIONS[method])(**params)
