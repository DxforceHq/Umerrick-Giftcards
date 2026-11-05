from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from .models import PriceItem

class PriceItemForm(forms.ModelForm):
    class Meta:
        model=PriceItem
        fields=['name','price']
        widgets={'name':forms.TextInput(attrs={'id':'new-item-name','placeholder':'Item name','maxlength':'180'}),
                 'price':forms.NumberInput(attrs={'id':'new-item-price','min':'0','step':'0.01','inputmode':'decimal','placeholder':'0.00'})}
    def clean_name(self):
        name=' '.join(self.cleaned_data['name'].split()).title()
        if not name: raise forms.ValidationError('Enter an item name.')
        existing=PriceItem.objects.filter(name__iexact=name)
        if self.instance.pk: existing=existing.exclude(pk=self.instance.pk)
        if existing.exists(): raise forms.ValidationError('An item with that name already exists.')
        return name
class GenerateForm(forms.Form):
    kind=forms.ChoiceField(choices=[('N10','₦10,000'),('N15','₦15,000'),('PCT10','10%')])
    count=forms.IntegerField(min_value=1,max_value=500,initial=1)
class StaffCreateForm(forms.Form):
    username=forms.RegexField(regex=r'^[\w.@+-]+$',max_length=150)
    password=forms.CharField(min_length=10,widget=forms.PasswordInput)
    def clean_username(self):
        username=self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists(): raise forms.ValidationError('That username is already in use.')
        return username
    def clean_password(self):
        password=self.cleaned_data['password']; password_validation.validate_password(password); return password
