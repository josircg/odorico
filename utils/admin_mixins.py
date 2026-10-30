class WidgetCustomAdminMixin:
    """
    Aplica estilos/widgets a campos do form apenas se eles existirem em
    base_fields. Campos readonly (variam por perfil de usuário) não estão
    presentes, evitando KeyError.

    field_styles:  {nome_campo: 'string css de estilo'}
    field_widgets: {nome_campo: instância OU classe de widget}
                   - instância já configurada -> usada como está
                   - classe sem configuração   -> instanciada (widget())
    """
    field_styles = {}
    field_widgets = {}

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        for name, style in self.field_styles.items():
            if name in form.base_fields:
                form.base_fields[name].widget.attrs['style'] = style
        for name, widget in self.field_widgets.items():
            if name in form.base_fields:
                form.base_fields[name].widget = (
                    widget() if isinstance(widget, type) else widget
                )
        return form
