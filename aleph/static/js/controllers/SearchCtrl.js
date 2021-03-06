aleph.controller('SearchCtrl', ['$scope', '$route', '$location', '$timeout', '$anchorScroll', '$http', '$uibModal', 'Collection', 'Entity', 'Authz', 'Alert', 'Document', 'Ingest', 'Role', 'Title', 'data', 'peek', 'alerts', 'metadata',
    function($scope, $route, $location, $timeout, $anchorScroll, $http, $uibModal, Collection, Entity, Authz, Alert, Document, Ingest, Role, Title, data, peek, alerts, metadata) {

  $scope.metadata = metadata;
  $scope.peek = peek;
  $scope.collectionFacet = [];
  $scope.authz = Authz;

  $scope.loadOffset = function(offset) {
    $scope.query.set('offset', offset);
    $anchorScroll();
  };

  function getAlert() {
    var alert = {};
    if ($scope.originalText.length >= 3) {
      alert.query_text = $scope.originalText;
    }
    if ($scope.query.getArray('entity').length == 1) {
      alert.entity_id = $scope.query.getArray('entity')[0];
    }
    return alert;
  };

  $scope.hasAlert = function() {
    return Alert.check(getAlert());
  };

  $scope.canCreateAlert = function() {
    if (!metadata.session.logged_in) {
      return false;
    }
    if ($scope.result.error) {
      return false;
    }
    return Alert.valid(getAlert());
  };

  $scope.toggleAlert = function() {
    return Alert.toggle(getAlert());
  };

  $scope.hasPeek = function() {
    return $scope.query.getQ().length > 1;
  };

  var initFacets = function(query, result) {
    if (result.error) {
      return;
    }
    $scope.collectionFacet = query.sortFacet(result.facets.collections.values, 'filter:collection_id');
  };

  $scope.$on('$routeUpdate', function() {
    reloadSearch();
  });

  var reloadSearch = function() {
    $scope.reportLoading(true);
    Document.search().then(function(data) {
      updateSearch(data);
    });
    if ($scope.hasPeek()) {
      Document.peek().then(function(peek) {
        $scope.peek = peek;
      });  
    } else {
      $scope.peek = {active: false};
    }
    
  };

  var updateSearch = function(data) {
    initFacets(data.query, data.result);
    $scope.query = data.query;
    $scope.result = data.result;
    $scope.queryString = data.query.toString();
    $scope.originalText = data.query.state.q ? data.query.state.q : '';
    
    if ($scope.query.getQ()) {
      Title.set("Search for '" + $scope.query.getQ() + "'", "documents");
    } else {
      Title.set("Search documents", "documents");  
    }
    $scope.reportLoading(false);
  };

  updateSearch(data);
}]);
