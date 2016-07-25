from __future__ import division
import pandas
import datetime
from model import (Vehicle, ChargingStation, Location, Parked, Driving,
                   BasicCarModel)


def from_excel(project, filename):
    """Read itineraries from an excel file. Excel header: Vehicle ID,
    Start time (hour), End time (hour), Distance (mi), P_max (W), Location,
    NHTS HH Wt.

    Args:
        project (Project): empty project
        filename (string): relative or absolute path to the excel file

    Return:
        project (Project): project assigned with vehicles
    """
    print('itinerary.from_excel(project, ' + filename + ')')
    print('Loading ...')

    # Day of the project
    date = project.date
    tot_sec = (date - datetime.datetime.utcfromtimestamp(0)).total_seconds()

    df = pandas.read_excel(io=filename, sheetname='Activity')
    df = df.drop('Nothing', axis=1)
    df = df.rename(columns={'Vehicle ID': 'id', 'State': 'state',
                            'Start time (hour)': 'start',
                            'End time (hour)': 'end',
                            'Distance (mi)': 'distance',
                            'P_max (W)': 'maximum_power',
                            'Location': 'location',
                            'NHTS HH Wt': 'weight'})
    from_mile_to_km = 1.60934

    # Initialize a car model for the project
    project.car_models = [BasicCarModel(name='Leaf')]

    # Initialize itinerary data for each vehicle
    # Group the dataframe by vehicle_id, and for each vehicle_id,
    for vehicle_id, vehicle_data in df.groupby('id'):
        # Create a vehicle instance
        vehicle = Vehicle(vehicle_id, project.car_models[0])
        vehicle.weight = vehicle_data.weight.iloc[0]

        # Create a list of activities parked and driving
        for index, row in vehicle_data.iterrows():
            # Round the start and end time to correspond with project.timestep
            start = datetime.datetime.utcfromtimestamp(tot_sec + int(
                (row['start'] * 3600) / project.timestep) * project.timestep)
            end = datetime.datetime.utcfromtimestamp(tot_sec + int(
                (row['end'] * 3600) / project.timestep) * project.timestep)

            # Accordingly to the state create a driving or parked activity
            if row['state'] in 'Driving':
                vehicle.activities.append(Driving(start, end, row['distance'] * from_mile_to_km))
            elif row['state'] in ['Parked', 'Charging']:
                vehicle.activities.append(
                    Parked(start, end, unique_location_category(row['location'], project)))
            else:
                print('State should either be Driving, Parked or Charging')
                print('State was: ' + str(row['state']))

        # Check time gap before appending vehicle to the project
        if not vehicle.check_activities(start_date=date,
                                        end_date=date + datetime.timedelta(days=1)):
            print('Itinerary does not respect the constraints')
            print(vehicle)
        project.vehicles.append(vehicle)

    # Initialize charging station at each location
    project.charging_stations = [ChargingStation(name='no_charger',
                                                 maximum_power=0,
                                                 minimum_power=0),
                                 ChargingStation(name='L1',
                                                 maximum_power=1440,
                                                 minimum_power=0),
                                 ChargingStation(name='L2',
                                                 maximum_power=7200,
                                                 minimum_power=0)]
    df2 = pandas.DataFrame(index=['no_charger', 'L1', 'L2'],
                           data={'charging_station': project.charging_stations,
                                 'probability': [0.0, 0.8, 0.2],
                                 'available': [float('inf'), float('inf'),
                                               float('inf')],
                                 'total': [float('inf'), float('inf'),
                                           float('inf')]})
    for location in project.locations:
        location.available_charging_station = df2

    print('')
    return project


def unique_location_category(location_category, project):
    """Compare input location category with locations in the project, return a
    new location and update the project or just return an existing location.

    Args:
        location_category (string): location category (Home, Work, ...)
        project (Project): current project

    Return:
        location (Location): either a new or an existing location
    """
    # Check if this location is matching any existing location in the project
    for existing_location in project.locations:
        if location_category in existing_location.category:
            return existing_location

    # If we reach this part of the code a new location need to be created
    new_location = Location(location_category, name=location_category + '01')
    project.locations.append(new_location)
    return new_location


def copy_append(project, nb_copies=2):
    """Copy the itinerary of each vehicle in the project.
    The copy is appended and a merge operation is applied to ensure a good blend.

    Args:
        project (Project): project
        nb_copies (int): number of copies to append

    Return:
        project (Project): new project with extended itineraries
    """
    number_of_merged = 0
    for vehicle in project.vehicles:
        new_activities = []
        for i_copy in range(0, nb_copies):
            # Manually copy all activities
            for activity in vehicle.activities:
                if isinstance(activity, Driving):
                    new_activities.append(Driving(activity.start + datetime.timedelta(days=1 + i_copy),
                                                  activity.end + datetime.timedelta(days=1 + i_copy),
                                                  activity.distance))
                elif isinstance(activity, Parked):
                    new_activities.append(Parked(activity.start + datetime.timedelta(days=1 + i_copy),
                                                 activity.end + datetime.timedelta(days=1 + i_copy),
                                                 activity.location))
        # Add new activities
        vehicle.activities.extend(new_activities)

        # Merge itineraries
        merged_activities = []
        skip = False
        for index, activity in enumerate(vehicle.activities):
            # Check if we have reached the last activity, if so exit loop
            if index == len(vehicle.activities) - 1:
                merged_activities.append(activity)
                break

            # Check if the activity has been merged during the previous iteration
            if skip:
                skip = False
                continue

            # Check for two parked activity in a row
            if (isinstance(activity, Parked) and
                    isinstance(vehicle.activities[index + 1], Parked)):
                # Check for matching names
                if (activity.location.category == vehicle.activities[index + 1].location.category and
                        activity.location.name == vehicle.activities[index + 1].location.name):
                    # Double check separately that times are matching
                    if activity.end == vehicle.activities[index + 1].start:
                        # Merge both activities
                        number_of_merged += 1
                        skip = True
                        activity.end = vehicle.activities[index + 1].end
                        merged_activities.append(activity)
                    else:
                        print activity
                        print vehicle.activities[index + 1]
                        print 'Merging issue'
                        merged_activities.append(activity)
                else:
                    merged_activities.append(activity)
            else:
                merged_activities.append(activity)

        vehicle.activities = merged_activities
        # Check time gap
        if not vehicle.check_activities(
                start_date=project.date, end_date=project.date + datetime.timedelta(days=1 + nb_copies)):
            print('Itinerary does not respect the constraints')
            print(vehicle)

    return project


def get_itineraries_statistics(project, verbose=False):
    """This function return 'number_of_trip', 'morning_start', 'total_distance',
    'went_to_work', 'last_trip_time' for each vehicle.
    note: the function do not handle vehicles with only 1 driving activity
    and no parked activities.

    Args:
        project (Project): project

    Return:
        stat (DataFrame): data frame with index vehicle ids
    """

    stat = pandas.DataFrame(index=[vehicle.id for vehicle in project.vehicles],
                            columns=['number_of_trip', 'morning_start', 'total_distance',
                                     'went_to_work', 'last_trip_time'])

    for vehicle in project.vehicles:

        # Count the number of trip in a day
        counter = 0
        for activity in vehicle.activities:
            if isinstance(activity, Driving):
                counter += 1
        stat.loc[vehicle.id, 'number_of_trip'] = counter

        # Find the morning start
        if isinstance(vehicle.activities[0], Parked):
            stat.loc[vehicle.id, 'morning_start'] = vehicle.activities[0].end
        elif isinstance(vehicle.activities[0], Driving):
            if verbose:
                print('Vehicle: ' + str(vehicle.id) + ' started the day driving.')
            stat.loc[vehicle.id, 'morning_start'] = vehicle.activities[1].end

        # Find total distance traveled [km] and average distance
        counter = 0
        for activity in vehicle.activities:
            if isinstance(activity, Driving):
                counter += activity.distance
        stat.loc[vehicle.id, 'total_distance'] = counter

        # Went to work ?
        stat.loc[vehicle.id, 'went_to_work'] = False
        for activity in vehicle.activities:
            if isinstance(activity, Parked):
                if activity.location.category in ['Work']:
                    stat.loc[vehicle.id, 'went_to_work'] = True
                    break

        # When did you go back home ?
        if isinstance(vehicle.activities[-1], Parked):
            stat.loc[vehicle.id, 'last_trip_time'] = vehicle.activities[-1].start
        elif isinstance(vehicle.activities[-1], Driving):
            if verbose:
                print('Vehicle: ' + str(vehicle.id) + ' ended the day driving.')
            stat.loc[vehicle.id, 'last_trip_time'] = vehicle.activities[-2].start

    return stat
