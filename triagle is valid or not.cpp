// Auther Hamza Tahir
#include<iostream>
using namespace std;
int main()
{
	// Write a C/C++ program to check whether a triangle can be formed by the given value for the angles
	int angl1, angl2, angl3;
	cout<<"Enter the value to angle 1 : ";
	cin>>angl1;
	cout<<"Enter the value to angle 2 : ";
	cin>>angl2;
	cout<<"Enter the value to angle 3 : ";
	cin>>angl3;
	int sum = angl1+angl2+angl3;
	if(sum==180)
	{
		cout<<"The Triangle is valid";
	}
	else
	{
		cout<<"The Triangle is not valid";
	}
}
