/*jslint browser: true, nomen: true, unparam: true */
/*global App */

// Copyright 2014 Junta de Andalucia
//
// Licensed under the EUPL, Version 1.1 or - as soon they
// will be approved by the European Commission - subsequent
// versions of the EUPL (the "Licence");
// You may not use this work except in compliance with the
// Licence.
// You may obtain a copy of the Licence at:
//
// http://ec.europa.eu/idabc/eupl
//
// Unless required by applicable law or agreed to in
// writing, software distributed under the Licence is
// distributed on an "AS IS" basis,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
// express or implied.
// See the Licence for the specific language governing
// permissions and limitations under the Licence.

App.module("Job", function (Job, App, Backbone, Marionette, $, _) {
    "use strict";

    App.addInitializer(function () {
        // TODO load jobs
    });
});

App.module("Job.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.JobModel = Backbone.Model.extend({
        url: function () {
            var url = "/api/jobs/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        }
    });

    Models.JobCollection = Backbone.Collection.extend({
        model: Models.JobModel
    });
});

App.module("Job.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.NanoJob = Marionette.ItemView.extend({});

    Views.NanoEvents = Marionette.CompositeView.extend({
        itemView: Views.NanoJob
    });

    Views.Job = Marionette.ItemView.extend({});

    Views.Events = Marionette.CompositeView.extend({
        itemView: Views.Job
    });
});
