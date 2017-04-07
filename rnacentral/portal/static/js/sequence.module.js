(function() {

var xrefResourceFactory = function($resource) {
    return $resource(
        '/rna/:upi/xrefs/:taxid?page=:page',
        {upi: '@upi', taxid: '@taxid', page: '@page'},
        {
            get: {timeout: 5000}
        }
    );
};
xrefResourceFactory.$inject = ['$resource'];

var xrefsComponent = {
    bindings: {
        upi: '@',
        taxid: '@?'
    },
    controller: function() {
        $scope.xrefs = xrefResource.get(
            {upi: this.upi, taxid: this.taxid},
            function (data) {
                // hide loading spinner
            },
            function () {
                // display error
            }
        );
    },
    templateUrl: "/static/js/xrefs.html"
};

var rnaSequenceController = function($scope, xrefResource, DTOptionsBuilder, DTColumnDefBuilder) {
    $scope.xrefs = [{
        "id": 860,
        "firstName": "Superman",
        "lastName": "Yoda"
    }, {
        "id": 870,
        "firstName": "Foo",
        "lastName": "Whateveryournameis"
    }, {
        "id": 590,
        "firstName": "Toto",
        "lastName": "Titi"
    }, {
        "id": 803,
        "firstName": "Luke",
        "lastName": "Kyle"
    }];

    $scope.dtOptions = DTOptionsBuilder.newOptions()
        .withPaginationType('full_numbers')
        .withDisplayLength(2)
        .withDOM('pitrfl');

    $scope.dtColumnDefs = [
        DTColumnDefBuilder.newColumnDef(0),
        DTColumnDefBuilder.newColumnDef(1).notVisible(),
        DTColumnDefBuilder.newColumnDef(2).notSortable()
    ];

};
rnaSequenceController.$inject = ['$scope', 'xrefResource', 'DTOptionsBuilder', 'DTColumnDefBuilder'];


angular.module("rnaSequence", ['datatables', 'ngResource'])
    .factory("xrefResource", xrefResourceFactory)
    .controller("rnaSequenceController", rnaSequenceController)
    .component("xrefsComponent", xrefsComponent);

})();
