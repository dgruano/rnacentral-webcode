var sequenceSearchController = function($scope, $http, $timeout, $location, $q, $window, routes) {
    $scope.query = {
        sequence: '',
        submit_attempted: false,
        enqueued_at: moment(null).utc(),
        ended_at: moment(null).utc()
    };

    $scope.results = {
        id: null,
        alignments: [],
        count: null,
        next_page: null,
        exact_match: null
    };

    $scope.defaults = {
        polling_interval: 1000, // milliseconds

        // global variables duplicated with Django backend
        min_length: 10,
        max_length: 10000
    };

    $scope.defaults['messages'] = {
        get_results: 'Loading results',
        done: 'Done',
        failed: 'Error',
        submit_failed: 'There was a problem submitting your query. Please try again later or get in touch if the error persists.',
        job_failed: 'There was a problem with your query. Please try again later or get in touch if the error persists.',
        results_failed: 'There was a problem retrieving the results. Please try again later or get in touch if the error persists.',
        cancelled: 'The search was cancelled',
        queued: 'Queued',
        started: 'Running',
        poll_job_status: 'Waiting for results',
        submitting: 'Submitting query',
        loading_more_results: 'Loading more results',
        too_short: 'The sequence cannot be shorter than ' + $scope.defaults['min_length'].toString() + ' nucleotides'
    };

    $scope.ordering = [
        { sort_field: 'e_value', label: 'E-value (min to max) - default'},
        { sort_field: '-e_value', label: 'E-value (max to min)'},
        { sort_field: '-identity', label: 'Identity (max to min)' },
        { sort_field: 'identity', label: 'Identity: (min to max)' },
        { sort_field: '-query_coverage', label: 'Query coverage: (max to min)' },
        { sort_field: 'query_coverage', label: 'Query coverage: (min to max)' },
        { sort_field: '-target_coverage', label: 'Target coverage: (max to min)' },
        { sort_field: 'target_coverage', label: 'Target coverage: (min to max)' }
    ];

    $scope.params = {
        search_in_progress: false,
        error_message: '',
        status_message: '',
        show_alignments: true,
        selectedOrdering: $scope.ordering[0],
        initial_page_size: null
    };

    var timeout;

    // ########################################################################
    // #                        Data access functions                         #
    // ########################################################################

    /**
     * Retrieve results given a results url.
     */
    $scope.fetch_job_results = function(id, next_page) {
        $scope.params.search_in_progress = true;
        $scope.params.status_message = $scope.defaults.messages.get_results;
        id = id || $location.search().id;
        next_page = next_page || false;

        $http({
            url: routes.sequenceSearchResults({ jobId: id }),
            method: 'GET',
            params: {
                // ordering: $scope.params.selectedOrdering.sort_field + ',result_id',
                start: 0,
                size: 20,
                page_size: $scope.params.initial_page_size || 10
            }
        }).then(
            function(response) {
                $scope.results.count = response.data.count;
                if (next_page) {
                    $scope.results.alignments = $scope.results.alignments.concat(response.data.results);
                } else {
                    $scope.results.alignments = response.data.results;
                }
                if ($scope.params.initial_page_size) {
                    $scope.params.initial_page_size = null;
                }
                $scope.results.next_page = response.data.next;
                $scope.params.search_in_progress = false;
                $scope.params.status_message = $scope.defaults.messages.done;
                update_page_size();
                update_page_title();
            },
            function() {
                $scope.params.search_in_progress = false;
                $scope.params.status_message = $scope.defaults.messages.failed;
                $scope.params.error_message = $scope.defaults.messages.results_failed;
                update_page_title();
            }
        );
    };

    /**
     * Check job status using REST API.
     */
    var fetch_job_status = function(id) {
        $http({
            url: routes.sequenceSearchJobStatus({ jobId: id }),
            method: 'GET',
            ignoreLoadingBar: true
        }).then(
            function(response) {
                $scope.query.ended_at = moment(response.data.ended_at).utc();
                $scope.query.enqueued_at = moment(response.data.enqueued_at).utc();

                if (response.data.status === 'finished') {
                    $scope.fetch_job_results(response.data.id);
                }
                else if (response.data.status === 'failed') {
                    $scope.params.search_in_progress = false;
                    $scope.params.status_message = $scope.defaults.messages.failed;
                    $scope.params.error_message = $scope.defaults.messages.job_failed;
                    update_page_title();
                }
                else {
                    $scope.params.search_in_progress = true;
                    if (response.data.status === 'queued') {
                        $scope.params.status_message = $scope.defaults.messages.queued;
                    } else if (response.data.status === 'started') {
                        $scope.params.status_message = $scope.defaults.messages.started;
                    } else {
                        $scope.params.status_message = '';
                    }
                    timeout = setTimeout(function() {
                        fetch_job_status(id);
                        update_page_title();
                    }, $scope.defaults.polling_interval);
                }
            },
            function(response) {
                $scope.params.status_message = $scope.defaults.messages.failed;
                $scope.params.error_message = $scope.defaults.messages.results_failed;
            }
        );
    };

    /**
     * Retrieve sequence given an RNAcentral id using promises.
     */
    function fetch_rnacentral_sequence(sequenceOrUpi) {
        var deferred = $q.defer();
        if (sequenceOrUpi.match(/^URS[A-Fa-f0-9]{10}$/i)) {
            $http({ url: routes.apiRnaView({ upi: sequenceOrUpi }) }).then(function(response){
                $scope.query.sequence = '>' + response.data.rnacentral_id + '\n' + response.data.sequence;
                deferred.resolve($scope.query.sequence);
            });
        } else {
            deferred.resolve(sequenceOrUpi);
            return deferred.promise;
        }
        return deferred.promise;
    }

    /**
     * Post query to run a job.
     */
    function submit_job(input) {
        return $http({
            url: routes.sequenceSearchSubmitJob({}),
            method: 'POST',
            data: $.param({
                q: input.sequence,
                description: input.description
            }),
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        }).then(
            function(response) {
                // save query id
                $scope.results.id = response.data.id;

                // update url
                $location.search({'id': response.data.id});

                // begin polling for results
                fetch_job_status(response.data.id);
                update_page_title();
            },
            function(response) {
                $scope.params.error_message = $scope.defaults.messages.submit_failed;
                $scope.params.status_message = $scope.defaults.messages.failed;
                $scope.params.search_in_progress = false;
                update_page_title();
            }
        );
    }

    /**
     * Initiate sequence search.
     */
    var search = function(sequence) {
        $scope.results = {
            id: null,
            alignments: [],
            count: null,
            next_page: null,
            exact_match: null
        };

        // if sequence contains an rnacental_id/upi/urs, fetch the actual sequence
        fetch_rnacentral_sequence(sequence).then(function(sequence) {
            // Submit query and begin checking whether the results are ready.
            input = parse_input(sequence);
            if (!is_valid_sequence(input.sequence)) {
                return;
            }
            $scope.params.search_in_progress = true;
            $scope.params.error_message = '';
            $scope.params.status_message = $scope.defaults.messages.submitting;

            fetch_exact_match(sequence);
            submit_job(input);
        });
    };

    /**
     * Retrieve query information in order to load
     * the query sequence into the search box.
     */
    function fetch_query_info(query_id) {
        $http({
            url: $scope.defaults.query_info_endpoint,
            method: 'GET',
            params: {
                id: query_id
            }
        }).then(
            function(response) {
                if (response.data.description) {
                    $scope.query.sequence = '>' + response.data.description + '\n' + response.data.sequence;
                } else {
                    $scope.query.sequence = response.data.sequence;
                }
                $scope.query.enqueued_at = moment(response.data.enqueued_at).utc();
                $scope.query.ended_at = moment(response.data.ended_at).utc();
                fetch_exact_match(response.data.sequence);
            },
            function(response) {
                $scope.params.status_message = $scope.defaults.messages.failed;
                $scope.params.error_message = $scope.defaults.messages.results_failed;
            }
        );
    }

    /**
     * Use RNAcentral API to retrieve an exact match
     * to the query sequence.
     */
    function fetch_exact_match(sequence) {
        input = parse_input(sequence);
        var md5_hash = md5(input.sequence.toUpperCase().replace(/U/g, 'T'));
        var url = $scope.defaults.md5_endpoint + '?md5=' + md5_hash;
        $http({
            url: url,
            method: 'GET',
            params: { md5: md5_hash }
        }).then(function(response) {
            if (response.data.count > 0) {
                $scope.results.exact_match = response.data.results[0].rnacentral_id;
            }
        });
    }

    // ########################################################################
    // #         Controller functions to be called from html template         #
    // ########################################################################

    /**
     * Add standard Javascript isNaN function to the scope
     * so that it can be used in the template.
     */
    $scope.isNaN = isNaN;

    /**
     * Reset the form.
     */
    $scope.reset = function() {
        $location.search({});
        $scope.params.search_in_progress = false;
        $scope.query = {
            sequence: '',
            submit_attempted: false,
            enqueued_at: moment(null).utc(),
            ended_at: moment(null).utc()
        };
        $scope.results = {
            id: null,
            alignments: [],
            count: null,
            next_page: null,
            exact_match: null
        };
        $scope.params.status_message = '';
        $scope.params.error_message = '';
        $('textarea').focus();
        update_page_title();
    };

    /**
     * Launch the search from template.
     */
    $scope.sequence_search = function(sequence) {
        $scope.query.sequence = sequence;
        search(sequence);
    };

    /**
     * Format e_value.
     */
    $scope.format_evalue = function(e_value) {
        return parseFloat(e_value).toExponential(2);
    };

    /**
     * Toggle alignments button.
     */
    $scope.toggle_alignments = function() {
        $scope.params.show_alignments = !$scope.params.show_alignments;
        $('#toggle-alignments').html(function(i, text){
          var icon = '<i class="fa fa-align-justify"></i> ';
          return icon + (text.indexOf("Show alignments") > -1 ? "Hide alignments" : "Show alignments");
        });
    };

    /**
     * Calculate query sequence length
     * (without whitespace and fasta header).
     */
    $scope.get_query_length = function() {
        var text = document.getElementById("query-sequence").value;
        if (text.match(/^URS[A-Fa-f0-9]{10}$/)) {
            return 0;
        }
        input = parse_input(text);
        return input.sequence.length || 0;
    };

    /**
     * Reverse the query sequence in place and repeat the search.
     * This is helpful when the user accidentally types the sequence in 3' to 5' direction.
     */
    $scope.reverse_and_repeat_search = function() {
        var input = parse_input($scope.query.sequence);
        var reversed_sequence = input.sequence.split("").reverse().join("");
        var description_line = '';
        if (input.description) {
          description_line = '>' + input.description + '\n';
        }
        $scope.query.sequence = description_line + reversed_sequence;
        search($scope.query.sequence);
    };

    /**
     * Update the `ordering` url parameter
     * based on the current user selection.
     */
    $scope.update_ordering = function() {
        $location.search($.extend($location.search(), {
            ordering: $scope.params.selectedOrdering.sort_field
        }));
    };

    /**
     * Public method for submitting the query.
     */
    $scope.submit_query = function() {
        $scope.query.submit_attempted = true;
        if (!$scope.seqQueryForm.$valid) {
            return;
        }
        search($scope.query.sequence);
    };

    /**
     * Load more results.
     */
    $scope.load_more_results = function() {
        var next_page = true;
        $scope.fetch_job_results($scope.results.id, next_page);
    };

    /**
     * Scroll page to the top.
     */
    $scope.scroll_to_top = function() {
        $("html, body").animate({ scrollTop: "0px" });
    };

    // ########################################################################
    // #                         Utility functions                            #
    // ########################################################################

    /**
     * Parse fasta header, remove whitespace characters.
     */
    function parse_input(sequence) {
        var match = /(^>(.+)[\n\r])?([\s\S]+)/.exec(sequence);
        if (match) {
            return { sequence: match[3].replace(/\s/g, ''), description: match[2] || '' };
        } else {
            return { sequence: '', description: '' };
        }
    }

    /**
     * Check sequence length once the fasta header line is removed.
     */
    function is_valid_sequence(sequence) {
        if (sequence.length < $scope.defaults.min_length) {
            $scope.params.error_message = $scope.defaults.messages.too_short;
            $scope.params.status_message = $scope.defaults.messages.failed;
            return false;
        } else {
            return true;
        }
    }

    /**
     * Get current time.
     */
    $scope.get_time_elapsed = function() {
        return moment().diff($scope.query.enqueued_at);
    };

    /**
     * Show progress in page title.
     */
    function update_page_title() {
        if ($scope.params.status_message === $scope.defaults.messages.failed) {
            $window.document.title = 'Search failed';
        } else if ($scope.params.search_in_progress) {
            $window.document.title = 'Searching...';
        } else if ($scope.params.status_message === $scope.defaults.messages.done) {
            $window.document.title = 'Search done';
        } else {
            $window.document.title = 'Sequence search';
        }
    }

    /**
     * Update the `page_size` url parameter
     * based on the number of currently loaded alignments.
     */
    var update_page_size = function() {
        $location.search($.extend($location.search(), {
            page_size: $scope.results.alignments.length,
        }));
    };

    // ########################################################################
    // #                          Initialization                              #
    // ########################################################################

    /**
     * When the controller is first created:
     * - activate Bootstrap tooltips when the controller is created.
     * - retrieve search results if necessary
     */
    (function() {
        if ($location.url().indexOf("id=") > -1) {
            // load results, set their ordering based on the url parameter
            if ($location.search().ordering) {
                var ordering = $location.search().ordering;
                for (var i=0, len=$scope.ordering.length; i < len; i++) {
                    if ($scope.ordering[i].sort_field === ordering) {
                        $scope.params.selectedOrdering = $scope.ordering[i];
                    }
                }
            }

            $scope.results.id = $location.search().id;

            fetch_job_status($location.search().id);

            // TODO: re-write this functionality using new data
            // fetch_query_info($location.search().id);

            $scope.params.initial_page_size = $location.search().page_size || null;
        } else if ($location.search().q) {
            // start sequence search
            $scope.query.sequence = $location.search().q;
            search($scope.query.sequence);
        }

        $('body').tooltip({
            selector: '.help',
            delay: { show: 200, hide: 100 },
            container: 'body'
        });
    })();
};

angular.module("sequenceSearch", ['chieffancypants.loadingBar', 'ngResource', 'ngAnimate', 'ui.bootstrap'])
    .controller("SequenceSearchController", ['$scope', '$http', '$timeout', '$location', '$q', '$window', 'routes', sequenceSearchController]);
