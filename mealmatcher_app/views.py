from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, logout
from django.contrib.auth import login as django_login
from mealmatcher_app.models import UserProfile, Meal
from mealmatcher_app.forms import MealForm, DeleteMealForm
import datetime, random
#import pytz
from django.utils import timezone as django_timezone
import urllib2, re
# mailer lib
from post_office.models import EmailTemplate
from post_office import mail
from django.template.loader import render_to_string

# index is the app homepage
@login_required
def index(request):
	context_dict = {'user': request.user}
	return render(request, 'mealmatcher_app/index.html', context_dict)

# find-meals page
@login_required
def find_meals(request):
	username = request.user.username
	my_user_profile = UserProfile.objects.filter(user=request.user)[0]
	if request.method == 'POST': # http post, process the data
		form = MealForm(request.POST)
		badTime = False
		if form.is_valid():
			data = form.cleaned_data
			year = 2015
			date_md = data['date_mdy'].split('/')
			print date_md[0]
			month = int(date_md[0])
			day = int(date_md[1])

			date_time = data['date_time'].split('-')[0].split(':')
			hour = int(date_time[0])
			# hack for timezone to avoid confusion of objects -- DANGER
			#hour = int(date_time[0]) - 4 
			#if hour < 0: hour = hour + 12
			minute = int(date_time[1])
			

			datetime_obj = datetime.datetime(year, month, day, hour, minute)
			#eastern = pytz.timezone('US/Eastern') # attempt at timezones, did not work
			#fmt = '%Y-%m-%d %H:%M %Z%z'
			#datetime_obj = eastern.localize(datetime_obj)
			#print datetime_obj.strftime(fmt)
			location = data['location']
			meal_time = data['meal_time']
			attire1 = data['attire1']

			# check for multiple meals at the same mealtime -- prevent signup 
			same_time = list(Meal.objects.filter(meal_time=meal_time, users__user=User.objects.filter(username=username)))
			for meal in same_time:
				if (meal.date.month == month and meal.date.day == day):
					print 'Attempted signup at a time that already has a meal the user is in.'
					badTime = True

			if not badTime:
				possible_matches = Meal.objects.filter(date=datetime_obj, location=location, 
									meal_time=meal_time).exclude(users__user=User.objects.filter(username=username))
				filtered_matches = []
				# there are potential matches, remove already matched ones
				if possible_matches:                        
					for match in possible_matches:
						if not (match.is_matched()):  # this meal is not matched
							filtered_matches.append(match)
				possible_matches = filtered_matches
				# if there are still possible_matches, make the match, 				
				if possible_matches:
					matched_meal = random.choice(possible_matches)
					matched_meal.attire2 = attire1

					#mailer user
					user2 = matched_meal.users.all()[0].user.username

					matched_meal.users.add(my_user_profile)
					new_meal = None

					'''if not EmailTemplate.objects.all():
						EmailTemplate.objects.create(
							name='match_email',
							subject='Good Day, {{ name }}!',
							content='MEAL INCOMING, {{ name }}!',
							html_content='MEAL INCOMING, {{ name }}! DATE - {{ datetime }} MEAL - {{ meal }} LOCATION - {{ location }} YOUR GUEST ATTIRE - {{ attire }}',
						)'''

					#html_content=render_to_string('match_email_html.html'),

					#mailer view
					mail.send(
						[username + '@princeton.edu'],
						'princeton.meal.matcher@gmail.com',
						template='match_email',
						context={'name': username, 'datetime': datetime_obj, 'meal': meal_time, 'location': location, 'attire': matched_meal.attire1},
						priority='now',
					)
					mail.send(
						[user2 + '@princeton.edu'],
						'princeton.meal.matcher@gmail.com',
						template='match_email',
						context={'name': user2, 'datetime': datetime_obj, 'meal': meal_time, 'location': location, 'attire': matched_meal.attire2},
						priority='now',
					)

					print matched_meal.attire2
					matched_meal.users.add(my_user_profile)
					new_meal = matched_meal
					new_meal.save()

					#return HttpResponse('Made a match!')
				else: # no matches, make a new Meal and add it to the database
					new_meal = Meal(date = datetime_obj, location=location, meal_time=meal_time, attire1=attire1)
					new_meal.save()                     
					new_meal.users.add(my_user_profile)
					new_meal.save()
					#return HttpResponse('Made a new meal!')

				return view_meals(request, new_meal=new_meal)  # HACK(drew) redirecting to my meals page after meal creation AND ALSO passing an extra arg
		else: # for debugging only
			print form.errors
	else:
		form = MealForm()
		badTime = False
	today = django_timezone.now()
	context_dict = {'form':form, 'date': {'month':today.month, 'day':today.day}, 'badTime': badTime}
	return render(request, 'mealmatcher_app/findmeal.html', context_dict)
		# return HttpResponse("Find meals")

# view-meals page

'''
def view_meals(request):
	meals = Meal.objects.filter(users__user=request.user).order_by('date')
	newmeals = []
	for meal in meals:
		day_of_week = meal.date.strftime('%A')
		month_day = meal.date.strftime('%m/%d')
		meal_dict =  {'B': 'Breakfast', 'L': 'Lunch', 'D': 'Dinner'}
		meal_time = meal_dict[meal.meal_time]
		meal_hourmin = (meal.date - datetime.timedelta(hours=4)).strftime('%H:%M') # hack to get around no time zones
		location_dict = {'WH': 'Whitman', 'RM': 'Rocky/Mathey', 'BW': 'Butler/Wilson', 'F': 'Forbes'}
		location = location_dict[meal.location]
		is_matched = meal.is_matched()
		newmeal = {'day_of_week': day_of_week, 'month_day': month_day, 'meal_time': meal_time,
					 'meal_hourmin': meal_hourmin, 'location': location, 'is_matched': is_matched}
		newmeals.append(newmeal)
	context_dict = {'username':request.user.username, 'meals':newmeals}
'''

@login_required
def view_meals(request, new_meal=None, deleted_meal=None): # HACK(drew) new_meal extra arg so we can highlight it when redirecting after form submission
	meals = list(Meal.objects.filter(users__user=request.user).order_by('date'))
	expired_meals = []
	removed_meals = []
	for meal in meals:
		if meal.to_be_removed():
			meals.remove(meal)
			removed_meals.append(meal)
		elif meal.is_expired():
			meals.remove(meal)
			expired_meals.append(meal)

	my_user_profile = UserProfile.objects.filter(user=request.user)[0]
	if new_meal:
		meals.remove(new_meal)
		meals.insert(0, new_meal)
	context_dict = {'username':request.user.username, 'meals':meals, 'new_meal':new_meal, 'deleted_meal':deleted_meal, 
					'user_profile': my_user_profile, 'expired_meals': expired_meals, 'removed_meals': removed_meals}
	return render(request, 'mealmatcher_app/mymeals.html', context_dict)
	# return HttpResponse("View meals")

@login_required
def delete_meal(request):
	if request.method == 'POST': # http post, process the data
		print 'received a delete meal post'
		form = DeleteMealForm(request.POST)
		if form.is_valid():
			data = form.cleaned_data
			print(data['idToDelete'])
			matchingMeals = Meal.objects.filter(id=data['idToDelete'])
			if len(matchingMeals) >= 1:
				mealToDelete = matchingMeals[0]
				if not mealToDelete.is_matched():
					mealToDelete.delete()
				# TODO(drew) only allow dropping out if meal isn't too soon
				else:
					myProfile = UserProfile.objects.filter(user=request.user)[0]

					# make sure the remaining user is shifted to user1, i.e. shift the attire
					if mealToDelete.users.all()[0] == myProfile:
						mealToDelete.attire1 = mealToDelete.attire2
					mealToDelete.attire2 = None
					mealToDelete.users.remove(myProfile)
				return view_meals(request, deleted_meal=mealToDelete)
		else:
			print form.errors
		return view_meals(request)

# login page
def site_login(request):
	# user is logged in, redirect to index page
	if request.user.is_authenticated():
		return HttpResponseRedirect('/mealmatcher_app/')
	# user is not logged in. go through CAS stuff
	else: 
		ticket = request.GET.get('ticket')
		if not ticket:
			return HttpResponseRedirect('https://fed.princeton.edu/cas/login?service=http://localhost:8000/mealmatcher_app/login/')
		else:
			source = urllib2.urlopen('https://fed.princeton.edu/cas/serviceValidate?service=http://localhost:8000/mealmatcher_app/login/&ticket=' + ticket)
			content = source.read()
			if 'authenticationSuccess' in content:      # success in authentication
				regexp = re.search('<cas:user>.*</cas:user>', content)
				netid = regexp.group(0)[10:-11]
				if User.objects.filter(username=netid): # in the database. Log them in
					username = netid
					password = netid
					user = authenticate(username=username, password=password)
					if user: 
						django_login(request, user)
						return HttpResponseRedirect('/mealmatcher_app/')
					else:
						return HttpResponse('Fatal error trying to log in '+ netid)
				else:
					username = netid
					password = netid
					newuser = User(username=username, password=password, email= (netid + '@princeton.edu'))
					newuser.save()
					newuser.set_password(newuser.password)
					newuser.save()
					profile = UserProfile(user = newuser)
					profile.save()
					newuser = authenticate(username=username, password=password)
					django_login(request, newuser)
					return HttpResponseRedirect('/mealmatcher_app/')
			else: # redirect to try again
				#return HttpResponse('failure')
				return HttpResponseRedirect('https://fed.princeton.edu/cas/login?service=http://localhost:8000/mealmatcher_app/login/')



@login_required
def site_logout(request):
	logout(request) # Log user out of our system
	return HttpResponseRedirect('https://fed.princeton.edu/cas/logout') # Log user out of CAS system

