import json

from django.core.serializers.json import Serializer
from django.core import serializers
from django.db import models
from django.db.models import ManyToManyField
from django.db.models.fields.files import FieldFile

JSON_ALLOWED_OBJECTS = (dict,list,tuple,str,int,bool)

class CustomSerializer(Serializer):

    def serialize(self, queryset, **options):
        """
                    Serialize a queryset.
                    """

        self.options = options

        self.stream = options.pop("stream", self.stream_class())
        try:
            self.selected_fields = options.get("fields", [field.attname for field in queryset[0]._meta.fields])
        except TypeError:
            self.selected_fields = options.get("fields", [field.attname for field in queryset._meta.fields])

        many = self.options.pop('many', False)
        if many:
            options['fields'] = self.selected_fields
            return super(CustomSerializer, self).serialize(queryset, **options)

        self.use_natural_foreign_keys = options.pop('use_natural_foreign_keys', False)
        self.use_natural_primary_keys = options.pop('use_natural_primary_keys', False)
        progress_bar = self.progress_class(
            options.pop('progress_output', None), options.pop('object_count', 0)
        )

        self.start_serialization()
        self.first = True

        obj = queryset
        count = 1
        self.start_object(obj)
        # Use the concrete parent class' _meta instead of the object's _meta
        # This is to avoid local_fields problems for proxy models. Refs #17717.
        concrete_model = obj._meta.concrete_model
        for field in concrete_model._meta.local_fields:
            if field.serialize:
                if field.remote_field is None:
                    if self.selected_fields is None or field.attname in self.selected_fields:
                        self.handle_field(obj, field)
                else:
                    if self.selected_fields is None or field.attname[:-3] in self.selected_fields:
                        self.handle_fk_field(obj, field)
        for field in concrete_model._meta.many_to_many:
            if field.serialize:
                if self.selected_fields is None or field.attname in self.selected_fields:
                    self.handle_m2m_field(obj, field)
        self.end_object(obj)
        progress_bar.update(count)
        if self.first:
            self.first = False

        self.end_serialization()
        return self.getvalue()



    def end_object(self, obj):
        for field in self.selected_fields:
            if field == 'pk':
                continue
            elif field in self._current.keys():
                continue
            else:
                try:
                    if '__' in field:
                        fields = field.split('__')
                        value = obj
                        for f in fields:
                            value = getattr(value, f)
                        try:
                            if str(value):
                                if isinstance(value, FieldFile):
                                    self._current[field] = value.name
                                else:
                                    self._current[field] = value
                            else:
                                self._current[field] = '-'
                        except Exception: pass
                    else:
                        value = getattr(obj, field)
                        self._current[field] = json.loads(serializers.serialize('json', value.all()))
                except AttributeError: pass
        super(CustomSerializer, self).end_object(obj)
