#!/usr/bin/perl

# This file is a part of Metagam project.
#
# Metagam is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
# 
# Metagam is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Metagam.  If not, see <http://www.gnu.org/licenses/>.

use strict;
use utf8;
use lib ($0 =~ /(.*)\//) ? $1 . '/..' : '..';

use mg::instance;

my $inst = mg::instance->new;
my $db = $inst->sql->{dbh};

my ($last_period, %players, %known_players, %registered, %returned);

for my $row (@{$db->selectall_arrayref('select * from active_players order by period', {Slice=>{}})}) {

	if ($row->{period} ne $last_period) {
		flush();
		$last_period = $row->{period};
	}

	if (!$players{$row->{app}}->{$row->{player}}) {
		if ($known_players{$row->{app}}->{$row->{player}}++) {
			$returned{$row->{app}}++;
		} else {
			$registered{$row->{app}}++;
		}
	}
	$players{$row->{app}}->{$row->{player}} = $row->{period};
}

flush();

sub flush
{
	if ($last_period) {
		# flushing $last_period
		my $till = $db->selectrow_array('select date_sub(?, interval 14 day)', undef, $last_period);
		my (%abandoned, %active);
		while (my ($app, $pls) = each %players) {
			while (my ($player, $last_visit) = each %$pls) {
				if ($last_visit lt $till) {
					$abandoned{$app}++;
					delete $pls->{$player};
				} else {
					$active{$app}++;
				}
			}
			print "$last_period $app reg=$registered{$app}, aban=$abandoned{$app}, ret=$returned{$app}, act=$active{$app}\n";
			$db->do('update visits set registered=?, returned=?, abandoned=?, active=? where app=? and period=?', undef, int($registered{$app}), int($returned{$app}), int($abandoned{$app}), int($active{$app}), $app, $last_period);
		}
		%registered = ();
		%returned = ();
	}
}
