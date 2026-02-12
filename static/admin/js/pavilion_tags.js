/* static/admin/js/pavilion_tags.js */

django.jQuery(document).ready(function($) {
    // Группируем чекбоксы по категориям
    var $checkboxGroup = $('.grouped-checkboxes');

    if ($checkboxGroup.length) {
        var groups = $checkboxGroup.data('groups');
        var $container = $('<div class="grouped-checkboxes-container"></div>');

        // Перебираем группы
        $.each(groups, function(groupName, choices) {
            var $groupDiv = $('<div class="tag-group"></div>');
            $groupDiv.append('<h4>' + groupName + '</h4>');
            var $ul = $('<ul></ul>');

            // Находим чекбоксы для этой группы
            $.each(choices, function(index, choice) {
                var $checkbox = $checkboxGroup.find('input[value="' + choice[0] + '"]').closest('li');
                $ul.append($checkbox.clone());
            });

            $groupDiv.append($ul);
            $container.append($groupDiv);
        });

        // Заменяем содержимое
        $checkboxGroup.empty().append($container);
    }
});