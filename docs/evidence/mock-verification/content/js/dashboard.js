/*
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

/*
 * Add header in statistics table to group metrics by category
 * format
 *
 */
function summaryTableHeader(header) {
    var newRow = header.insertRow(-1);
    newRow.className = "tablesorter-no-sort";
    var cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Requests";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 3;
    cell.innerHTML = "Executions";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 7;
    cell.innerHTML = "Response Times (ms)";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Throughput";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 2;
    cell.innerHTML = "Network (KB/sec)";
    newRow.appendChild(cell);
}

/*
 * Populates the table identified by id parameter with the specified data and
 * format
 *
 */
function createTable(table, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var tableRef = table[0];

    // Create header and populate it with data.titles array
    var header = tableRef.createTHead();

    // Call callback is available
    if(headerCreator) {
        headerCreator(header);
    }

    var newRow = header.insertRow(-1);
    for (var index = 0; index < info.titles.length; index++) {
        var cell = document.createElement('th');
        cell.innerHTML = info.titles[index];
        newRow.appendChild(cell);
    }

    var tBody;

    // Create overall body if defined
    if(info.overall){
        tBody = document.createElement('tbody');
        tBody.className = "tablesorter-no-sort";
        tableRef.appendChild(tBody);
        var newRow = tBody.insertRow(-1);
        var data = info.overall.data;
        for(var index=0;index < data.length; index++){
            var cell = newRow.insertCell(-1);
            cell.innerHTML = formatter ? formatter(index, data[index]): data[index];
        }
    }

    // Create regular body
    tBody = document.createElement('tbody');
    tableRef.appendChild(tBody);

    var regexp;
    if(seriesFilter) {
        regexp = new RegExp(seriesFilter, 'i');
    }
    // Populate body with data.items array
    for(var index=0; index < info.items.length; index++){
        var item = info.items[index];
        if((!regexp || filtersOnlySampleSeries && !info.supportsControllersDiscrimination || regexp.test(item.data[seriesIndex]))
                &&
                (!showControllersOnly || !info.supportsControllersDiscrimination || item.isController)){
            if(item.data.length > 0) {
                var newRow = tBody.insertRow(-1);
                for(var col=0; col < item.data.length; col++){
                    var cell = newRow.insertCell(-1);
                    cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];
                }
            }
        }
    }

    // Add support of columns sort
    table.tablesorter({sortList : defaultSorts});
}

$(document).ready(function() {

    // Customize table sorter default options
    $.extend( $.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    var data = {"OkPercent": 98.2905982905983, "KoPercent": 1.7094017094017093};
    var dataset = [
        {
            "label" : "FAIL",
            "data" : data.KoPercent,
            "color" : "#FF6347"
        },
        {
            "label" : "PASS",
            "data" : data.OkPercent,
            "color" : "#9ACD32"
        }];
    $.plot($("#flot-requests-summary"), dataset, {
        series : {
            pie : {
                show : true,
                radius : 1,
                label : {
                    show : true,
                    radius : 3 / 4,
                    formatter : function(label, series) {
                        return '<div style="font-size:8pt;text-align:center;padding:2px;color:white;">'
                            + label
                            + '<br/>'
                            + Math.round10(series.percent, -2)
                            + '%</div>';
                    },
                    background : {
                        opacity : 0.5,
                        color : '#000'
                    }
                }
            }
        },
        legend : {
            show : true
        }
    });

    // Creates APDEX table
    createTable($("#apdexTable"), {"supportsControllersDiscrimination": true, "overall": {"data": [0.9631410256410257, 500, 1500, "Total"], "isController": false}, "titles": ["Apdex", "T (Toleration threshold)", "F (Frustration threshold)", "Label"], "items": [{"data": [0.9047619047619048, 500, 1500, "TX-01 Browse"], "isController": true}, {"data": [1.0, 500, 1500, "S06 User profile (deep dive, chained by userId)"], "isController": false}, {"data": [1.0, 500, 1500, "S01c Categories"], "isController": false}, {"data": [1.0, 500, 1500, "S01e Course Detail (chained from catalog)"], "isController": false}, {"data": [0.9166666666666666, 500, 1500, "TX-02 Explore"], "isController": true}, {"data": [0.875, 500, 1500, "S01b Certificates"], "isController": false}, {"data": [1.0, 500, 1500, "MON Server metrics"], "isController": false}, {"data": [1.0, 500, 1500, "S04 User profile (chained)"], "isController": false}, {"data": [1.0, 500, 1500, "S01d Course Catalog (filtered by category)"], "isController": false}, {"data": [0.7142857142857143, 500, 1500, "S03b Certificates (explore)"], "isController": false}, {"data": [1.0, 500, 1500, "S01a My Courses"], "isController": false}, {"data": [1.0, 500, 1500, "S00 Login (CSV credentials)"], "isController": false}, {"data": [1.0, 500, 1500, "S03c Categories (explore)"], "isController": false}, {"data": [1.0, 500, 1500, "S03a My Courses (explore)"], "isController": false}, {"data": [1.0, 500, 1500, "S05 My Courses (deep dive)"], "isController": false}, {"data": [1.0, 500, 1500, "S02 User profile (chained)"], "isController": false}, {"data": [1.0, 500, 1500, "S00b Re-login (fallback)"], "isController": false}, {"data": [1.0, 500, 1500, "S08 Enrollment status (chained by course + cert)"], "isController": false}, {"data": [0.9117647058823529, 500, 1500, "TX-03 Deep Dive"], "isController": true}, {"data": [1.0, 500, 1500, "S07 Certificates (signed, retryable, chained by course)"], "isController": false}, {"data": [1.0, 500, 1500, "S03d Course Search (chained keyword)"], "isController": false}]}, function(index, item){
        switch(index){
            case 0:
                item = item.toFixed(3);
                break;
            case 1:
            case 2:
                item = formatDuration(item);
                break;
        }
        return item;
    }, [[0, 0]], 3);

    // Create statistics table
    createTable($("#statisticsTable"), {"supportsControllersDiscrimination": true, "overall": {"data": ["Total", 234, 4, 1.7094017094017093, 129.33333333333326, 0, 4791, 47.0, 230.5, 281.75, 4069.650000000004, 2.5770073675979868, 2.5339453955265796, 0.6596418723775647], "isController": false}, "titles": ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"], "items": [{"data": ["TX-01 Browse", 42, 2, 4.761904761904762, 382.2857142857142, 0, 4791, 151.0, 335.5, 3718.4500000000057, 4791.0, 0.46749257020736634, 1.1119796884217674, 0.2605949329927316], "isController": true}, {"data": ["S06 User profile (deep dive, chained by userId)", 15, 0, 0.0, 39.4, 25, 57, 37.0, 55.8, 57.0, 57.0, 0.19541682408577496, 0.0528617776091403, 0.04564814875128649], "isController": false}, {"data": ["S01c Categories", 9, 0, 0.0, 39.77777777777778, 28, 55, 36.0, 55.0, 55.0, 55.0, 0.10484866842191104, 0.043721075601714864, 0.025495428161187356], "isController": false}, {"data": ["S01e Course Detail (chained from catalog)", 9, 0, 0.0, 35.888888888888886, 20, 44, 37.0, 44.0, 44.0, 44.0, 0.10544568375667822, 0.046647358146264875, 0.02687629244188771], "isController": false}, {"data": ["TX-02 Explore", 24, 2, 8.333333333333334, 143.08333333333331, 61, 352, 103.5, 324.0, 347.5, 352.0, 0.3042712070692344, 0.4606410534756647, 0.14509091290870596], "isController": true}, {"data": ["S01b Certificates", 16, 2, 12.5, 218.0625, 90, 300, 223.5, 293.0, 300.0, 300.0, 0.2010126009774238, 0.05557782485520812, 0.04662157493372866], "isController": false}, {"data": ["MON Server metrics", 17, 0, 0.0, 5.352941176470588, 2, 15, 6.0, 10.199999999999996, 15.0, 15.0, 0.21195686054485383, 0.06251071473100181, 0.05795695405523347], "isController": false}, {"data": ["S04 User profile (chained)", 24, 0, 0.0, 39.458333333333336, 24, 59, 40.5, 52.0, 57.75, 59.0, 0.29174720105028995, 0.07891989715911163, 0.06738106743007184], "isController": false}, {"data": ["S01d Course Catalog (filtered by category)", 9, 0, 0.0, 36.44444444444444, 25, 47, 35.0, 47.0, 47.0, 47.0, 0.10562388508121304, 0.2666957254600507, 0.029775483229274247], "isController": false}, {"data": ["S03b Certificates (explore)", 7, 2, 28.571428571428573, 226.14285714285714, 105, 318, 227.0, 318.0, 318.0, 318.0, 0.10618126659082291, 0.027908134243458477, 0.024871421122487677], "isController": false}, {"data": ["S01a My Courses", 16, 0, 0.0, 72.06250000000001, 43, 100, 65.0, 99.3, 100.0, 100.0, 0.2214870084026634, 0.7540075305582856, 0.05153249975774858], "isController": false}, {"data": ["S00 Login (CSV credentials)", 1, 0, 0.0, 86.0, 86, 86, 86.0, 86.0, 86.0, 86.0, 11.627906976744185, 3.87218386627907, 3.6110101744186047], "isController": false}, {"data": ["S03c Categories (explore)", 5, 0, 0.0, 39.6, 28, 48, 41.0, 48.0, 48.0, 48.0, 0.15392666933472895, 0.06418621856047779, 0.03610662692793154], "isController": false}, {"data": ["S03a My Courses (explore)", 7, 0, 0.0, 72.28571428571429, 52, 95, 73.0, 95.0, 95.0, 95.0, 0.09300348098743125, 0.31661145968963406, 0.02260212944755932], "isController": false}, {"data": ["S05 My Courses (deep dive)", 16, 0, 0.0, 77.37500000000001, 48, 109, 76.5, 100.60000000000001, 109.0, 109.0, 0.18464450163294982, 0.6285846998949834, 0.04296050050200224], "isController": false}, {"data": ["S02 User profile (chained)", 39, 0, 0.0, 38.61538461538462, 22, 61, 38.0, 52.0, 56.0, 61.0, 0.47761340256686585, 0.12919815674904475, 0.10971617976633682], "isController": false}, {"data": ["S00b Re-login (fallback)", 4, 0, 0.0, 68.0, 43, 97, 66.0, 97.0, 97.0, 97.0, 1.2987012987012987, 0.43247767857142855, 0.3969663149350649], "isController": false}, {"data": ["S08 Enrollment status (chained by course + cert)", 15, 0, 0.0, 71.53333333333333, 43, 97, 76.0, 94.0, 97.0, 97.0, 0.19352341633337633, 0.18312909221390786, 0.05218580667010708], "isController": false}, {"data": ["TX-03 Deep Dive", 17, 0, 0.0, 588.7647058823529, 0, 3614, 410.0, 1159.5999999999979, 3614.0, 3614.0, 0.19366818943027375, 0.8775144823932831, 0.19601561520978822], "isController": true}, {"data": ["S07 Certificates (signed, retryable, chained by course)", 15, 0, 0.0, 240.13333333333335, 161, 366, 242.0, 327.6, 366.0, 366.0, 0.19260647928196306, 0.055299125887594856, 0.07620244626279228], "isController": false}, {"data": ["S03d Course Search (chained keyword)", 5, 0, 0.0, 40.0, 29, 47, 41.0, 47.0, 47.0, 47.0, 0.20816853324451476, 0.08688596787959532, 0.057774899558682716], "isController": false}]}, function(index, item){
        switch(index){
            // Errors pct
            case 3:
                item = item.toFixed(2) + '%';
                break;
            // Mean
            case 4:
            // Mean
            case 7:
            // Median
            case 8:
            // Percentile 1
            case 9:
            // Percentile 2
            case 10:
            // Percentile 3
            case 11:
            // Throughput
            case 12:
            // Kbytes/s
            case 13:
            // Sent Kbytes/s
                item = item.toFixed(2);
                break;
        }
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // Create error table
    createTable($("#errorsTable"), {"supportsControllersDiscrimination": false, "titles": ["Type of error", "Number of errors", "% in errors", "% in all samples"], "items": [{"data": ["Filter: [0]['id'] can only be applied to arrays. Current context is: {status=declined, detail=certificate service timeout}", 2, 50.0, 0.8547008547008547], "isController": false}, {"data": ["Filter: [0]['course_title'] can only be applied to arrays. Current context is: {status=declined, detail=certificate service timeout}", 2, 50.0, 0.8547008547008547], "isController": false}]}, function(index, item){
        switch(index){
            case 2:
            case 3:
                item = item.toFixed(2) + '%';
                break;
        }
        return item;
    }, [[1, 1]]);

        // Create top5 errors by sampler
    createTable($("#top5ErrorsBySamplerTable"), {"supportsControllersDiscrimination": false, "overall": {"data": ["Total", 234, 4, "Filter: [0]['id'] can only be applied to arrays. Current context is: {status=declined, detail=certificate service timeout}", 2, "Filter: [0]['course_title'] can only be applied to arrays. Current context is: {status=declined, detail=certificate service timeout}", 2, "", "", "", "", "", ""], "isController": false}, "titles": ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"], "items": [{"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": ["S01b Certificates", 16, 2, "Filter: [0]['id'] can only be applied to arrays. Current context is: {status=declined, detail=certificate service timeout}", 2, "", "", "", "", "", "", "", ""], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": ["S03b Certificates (explore)", 7, 2, "Filter: [0]['course_title'] can only be applied to arrays. Current context is: {status=declined, detail=certificate service timeout}", 2, "", "", "", "", "", "", "", ""], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}, {"data": [], "isController": false}]}, function(index, item){
        return item;
    }, [[0, 0]], 0);

});
