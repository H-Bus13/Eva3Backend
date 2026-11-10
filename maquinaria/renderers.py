from django import forms
from django.forms.boundfield import BoundField
from django.forms.renderers import DjangoTemplates


class BootstrapBoundField(BoundField):
    def build_widget_attrs(self, attrs, widget=None):
        widget = widget or self.field.widget
        attrs = super().build_widget_attrs(attrs, widget)
        # Un único renderer adapta los formularios existentes. Los grupos
        # de radios/casillas conservan su estructura para no romper etiquetas.
        if not widget.is_hidden and not isinstance(widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
            clase = "form-check-input" if isinstance(widget, forms.CheckboxInput) else "form-select" if isinstance(widget, forms.Select) else "form-control"
            attrs["class"] = " ".join(filter(None, [widget.attrs.get("class"), attrs.get("class"), clase, "is-invalid" if self.errors else ""]))
        return attrs

    def label_tag(self, contents=None, attrs=None, label_suffix=None, tag=None):
        attrs = dict(attrs or {})
        attrs.setdefault("class", "form-check-label" if isinstance(self.field.widget, forms.CheckboxInput) else "form-label")
        return super().label_tag(contents=contents, attrs=attrs, label_suffix=label_suffix, tag=tag)


class BootstrapFormRenderer(DjangoTemplates):
    bound_field_class = BootstrapBoundField
