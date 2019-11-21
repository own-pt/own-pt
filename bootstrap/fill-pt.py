from rdflib import Graph, Namespace, Literal, URIRef
from rdflib.term import Node
from rdflib.namespace import RDF, OWL, SKOS, RDFS, split_uri
import click

# This script is very ad hoc and has lots of hardcoded stuff; this is
# by design, since it is only meant to be run once as bootstrap for
# the text files. run
## python <this-file>.py --help
# for options


WN30PT = Namespace("https://w3id.org/own-pt/wn30-pt/instances/") # not used (yet)
WN30 = Namespace("https://w3id.org/own-pt/wn30/schema/")
WN_CONTAINS_WORDSENSE = WN30["containsWordSense"]
WN_SAME_AS = OWL["sameAs"]
WN_LEXICAL_FORM = WN30["lexicalForm"]
WN_WORD = WN30["word"]
WN_LANG = WN30["lang"]
WN_LEXICAL_ID = WN30["lexicalId"]
WN_GLOSS = WN30["gloss"]
WN_EXAMPLE = WN30["example"]
WN_LEXICOGRAPHER_FILE = WN30["lexicographerFile"]
FORBIDDEN_PREDICATE_LIST = [WN_LANG, WN_CONTAINS_WORDSENSE, WN_SAME_AS, SKOS["inScheme"], WN_GLOSS, WN30["synsetId"], RDF["type"], WN_EXAMPLE]
FORBIDDEN_PREDICATES = {pred: True for pred in FORBIDDEN_PREDICATE_LIST}

PT = Literal("pt")
EN = Literal("en")

@click.command()
@click.argument('input_file', type=click.File(mode="rb"), required=True)
@click.argument('output_file', type=click.Path(dir_okay=False,resolve_path=True),
                required=True)
@click.option('-f', '--rdf-file-format', 'rdf_file_format', type=click.STRING, default='nt', show_default=True,
              help="Type of RDF input file. Must be accepted by RDFlib.")
def main(input_file, rdf_file_format, output_file):
    graph = Graph()
    graph.parse(input_file, format=rdf_file_format)
    go(graph) # modifies graph
    graph.serialize(output_file, format="nt")
    return None

def go(graph):
    def en_to_pt_synset(en_synset):
        return graph.value(en_synset,WN_SAME_AS,default=False,any=False)
    def synset_minimal_wordsense(synset):
        wordsenses = graph.objects(synset, WN_CONTAINS_WORDSENSE)
        word_forms = list(map(lambda ws: graph.value(graph.value(ws, WN_WORD, any=False), WN_LEXICAL_FORM, any=False), wordsenses))
        if None in word_forms or not word_forms:
            print(synset)
        min_word_form = min(word_forms)
        return min_word_form
    def handle_spaces(string):
        return string.replace(" ", "_").strip()
    #
    # use list so that it is safe to add sameAs relations while we
    # iterate over them
    same_as_relations = list(graph.triples((None, WN_SAME_AS, None)))
    # fill up info from English synset to Portuguese one
    for (en_synset, _, pt_synset) in same_as_relations:
        graph.add((pt_synset, WN_LANG, PT))
        graph.add((en_synset, WN_LANG, EN))
        # everything else
        for (_, pred, obj) in graph.triples((en_synset, None, None)):
            if pred not in FORBIDDEN_PREDICATES:
                obj = en_to_pt_synset(obj) or obj
                graph.add((pt_synset,pred,obj))
        for (subj,pred,_) in graph.triples((None, None, en_synset)):
            if pred not in FORBIDDEN_PREDICATES:
                subj = en_to_pt_synset(subj) or subj
                graph.add((subj,pred,pt_synset))
        ## add dummy stuff if missing in Portuguese
        # gloss/definition
        if (pt_synset, WN_GLOSS, None) not in graph:
            # doing the split here or else the wn2text script will do
            # it for us and then we would have spurious English
            # examples in Portuguese
            english_definition = graph.value(en_synset, WN_GLOSS).split("; \"")[0].strip()
            graph.add((pt_synset, WN_GLOSS, Literal("@en_{}".format(english_definition))))
        # wordsenses and words
        wordsenses = list(graph.objects(pt_synset, WN_CONTAINS_WORDSENSE))
        # if we don't force the generator the test below is moot
        if wordsenses:
            lexical_forms_seen = {} # to remove duplicate wordsenses
                                    # (usually one form with spaces
                                    # and the other with underscores)
            for wordsense in wordsenses:
                word = graph.value(wordsense, WN_WORD)
                if not word:
                    (_, wordsense_name) = split_uri(wordsense)
                    word = WN30PT["word-{}".format(wordsense_name)]
                    graph.add((wordsense, WN_WORD, word))
                new_lexical_form = graph.value(word, WN_LEXICAL_FORM) or graph.value(wordsense, RDFS.label)
                lexical_form = Literal(handle_spaces(new_lexical_form))
                if lexical_forms_seen.get(lexical_form, None):
                    # remove duplicate wordsense
                    graph.remove((None, None, wordsense))
                    graph.remove((wordsense, None, None))
                else:
                    lexical_forms_seen[lexical_form] = True
                    # remove previous lexical_forms
                    graph.remove((word, WN_LEXICAL_FORM, None))
                    # add new lexical_form (with underscores instead of spaces)
                    graph.add((word, WN_LEXICAL_FORM, lexical_form))
        else:
            (_, synset_uri) = split_uri(pt_synset)
            english_wordsenses = graph.objects(en_synset, WN_CONTAINS_WORDSENSE)
            for ix, english_wordsense in enumerate(english_wordsenses):
                wordsense = WN30PT["wordsense-{}-{}.".format(synset_uri, ix)]
                graph.add((pt_synset, WN_CONTAINS_WORDSENSE, wordsense))
                word = WN30PT["word-{}-{}".format(synset_uri, ix)]
                graph.add((wordsense, WN_WORD, word))
                english_lexical_form = graph.value(graph.value(english_wordsense, WN_WORD), WN_LEXICAL_FORM)
                graph.add((word, WN_LEXICAL_FORM, Literal("@en_{}".format(english_lexical_form))))
    # add lexical ids and lexical forms if missing
    for lexfile in set(graph.objects(predicate=WN_LEXICOGRAPHER_FILE)):
        count = {}
        all_synsets = graph.subjects(predicate=WN_LEXICOGRAPHER_FILE, object=lexfile)
        synsets = filter(lambda s: graph.value(s, WN_LANG) == PT, all_synsets)
        for synset in sorted(synsets, key=synset_minimal_wordsense):
            for wordsense in graph.objects(synset,WN_CONTAINS_WORDSENSE):
                word = graph.value(wordsense, WN_WORD)
                if (wordsense, WN_LEXICAL_ID, None) not in graph:
                    lexical_form = graph.value(word, WN_LEXICAL_FORM)
                    lexical_id = count.get(lexical_form, 0)
                    graph.add((wordsense, WN_LEXICAL_ID, Literal("{}".format(lexical_id))))
                    count[lexical_form] = lexical_id + 1
    for en_synset, pt_synset in graph.subject_objects(WN_SAME_AS):
        graph.remove((en_synset, WN_SAME_AS, pt_synset))
        graph.add((pt_synset, WN_SAME_AS, en_synset))
    return None

###
## fix multiple glosses: add one as definition and the other as
## examples
WN_DEFINITION = WN30['definition']
def fix_multiple_glosses(graph):
    for synset in graph.subjects(WN_LANG, PT):
        glosses = list(graph.objects(synset, WN_DEFINITION))
        if len(glosses) > 1:
            graph.remove((synset, WN_DEFINITION, None))
            graph.add((synset, WN_DEFINITION, Literal(glosses[0].strip())))
            for gloss in glosses[1:]:
                example = Literal("_GLOSS_: ") + gloss
                graph.add((synset, WN_EXAMPLE, Literal(example.strip())))
    return None

###
## fix wrong URIs
WN_DERIVATIONALLY_RELATED = WN30["derivationallyRelated"]

def fix_derivationally_related_wrong_uris(graph):
    for subj, obj in graph.subject_objects(WN_DERIVATIONALLY_RELATED):
        if (None, WN_CONTAINS_WORDSENSE, obj) not in graph:
            obj = r.URIRef(obj.replace("-a-", "-s-"))
            assert (None, WN_CONTAINS_WORDSENSE, obj) in graph, obj
            graph.add((subj, WN_DERIVATIONALLY_RELATED, obj))

###
## fix () in words
def fix_parentheses_in_words(graph):
    for subj, original_lexical_form in graph.subject_objects(WN_LEXICAL_FORM):
        lexical_form = str(original_lexical_form)
        if '(' in lexical_form or ')' in lexical_form:
            print(lexical_form)
            lexical_form = lexical_form.replace("(", "{{").replace(")", "}}")
            graph.remove((subj, WN_LEXICAL_FORM, original_lexical_form))
            graph.add((subj, WN_LEXICAL_FORM, Literal(lexical_form)))
    return None
        

if __name__ == '__main__':
    main()
