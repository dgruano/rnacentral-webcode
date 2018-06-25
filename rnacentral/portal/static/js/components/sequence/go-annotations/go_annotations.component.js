var go_annotations = {
    bindings: {
        upi: '=',
        taxid: '=',
        showGoAnnotations: '&',
    },

    controller: ['$http', 'routes', function($http, routes) {
        var ctrl = this;

        var sourceUrls = {
            "bhf-ucl": "https://www.ucl.ac.uk/functional-gene-annotation/cardiovascular/projects",
            "sgd": "https://www.yeastgenome.org/",
            "mgi": "http://www.informatics.jax.org",
            "uniprot": "http://www.uniprot.org",
            "goc": "http://geneontology.org",
            "aruk-ucl": "http://www.ucl.ac.uk/functional-gene-annotation/neurological",
            "parkinsonsuk-ucl": "http://www.ucl.ac.uk/functional-gene-annotation/neurological",
        };

        var annotationOrdering = function(annotation) {
            var qualifier = {
                "involved_in": 10,
                "enables": 20, 
                "contributes_to": 30,
                "colocalizes_with": 40,
                "part_of": 50,
                "__unknown__": 60,
            };

            var evidence = {
                "ECO:0000314": 1,
                "ECO:0000315": 2,
                "ECO:0000353": 3,
                "ECO:0000316": 4,
                "ECO:0000270": 5,
                "__unknown__": 6,
            };

            return (qualifier[annotation.qualifier] || qualifier.__unknown__) +
                (evidence[annotation.evidence_code_id] || evidence.__unknown__);
        };

        ctrl.$onInit = function() {
            ctrl.chart_data = '';
            ctrl.fetchGoTerms().then(
                function(response) {
                    ctrl.go_annotations = response.data;
                    ctrl.go_annotations.sort(ctrl.compareAnnotations);

                    ctrl.go_annotations.forEach(function(annotation) {
                        var key = annotation.assigned_by.toLowerCase();
                        annotation.assigned_url = sourceUrls[key];
                        annotation.needs_explanation = annotation.evidence_code_id == 'ECO:0000307';
                        if (annotation.needs_explanation) {
                            annotation.explanation_url = 'http://wiki.geneontology.org/index.php/No_biological_Data_available_(ND)_evidence_code';
                        }
                    });

                    if (ctrl.go_annotations.length) {
                        ctrl.showGoAnnotations();
                    }
                },
                function(response) {
                    ctrl.error = "Failed to fetch GO annotations";
                }
            );
        };

        ctrl.compareAnnotations = function(first, second) {
            return annotationOrdering(first) - annotationOrdering(second);
        };

        ctrl.fetchGoTerms = function() {
            return $http.get(
                routes.apiGoTermsView({ upi: ctrl.upi, taxid: ctrl.taxid }),
                { timeout: 5000 }
            );
        };

        ctrl.openGoChartModal = function(term_id) {
            var ontology = term_id.split(':')[0].toLowerCase();
            var png = routes.quickGoChart({ ontology: ontology, term_ids: term_id });
            ctrl.modal_status = 'loading';
            $('#go-annotation-chart-modal').modal();

            $http.get(png, { timeout: 5000 }).then(
                function(response) {
                    ctrl.modal_status = 'loaded';
                    ctrl.chart_data = 'data:image/png;charset=utf-8;base64,' + response.data;
                },
                function(error) {
                    ctrl.modal_status = 'failed';
                });
        };
    }],

    templateUrl: '/static/js/components/sequence/go-annotations/go_annotations.html'
};

angular.module("rnaSequence").component("goAnnotations", go_annotations);